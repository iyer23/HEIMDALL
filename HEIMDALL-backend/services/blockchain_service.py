"""
HEIMDALL — Blockchain Evidence Service (additive)
SIH 2026 · PS 26188

Tamper-evident anchoring of screening results.

WHAT GOES ON-CHAIN (never any PII):
  - bytes32 screening ID (opaque code like "HM-1A2B3C4D5E6F")
  - SHA-256 hash of the result's integrity fields (no OCR text, no names,
    no DOB, no addresses, no document numbers, no images)
  - numeric risk score + decision code
  - registration timestamp

WHAT STAYS OFF-CHAIN: everything else. Images and OCR text never leave
HEIMDALL's own storage.

MODES
  sepolia  — BLOCKCHAIN_RPC_URL + BLOCKCHAIN_PRIVATE_KEY + CONTRACT_ADDRESS
             are configured: anchors via a real Ethereum-compatible testnet.
  demo     — config missing: anchors into a local tamper-evident ledger table
             and CLEARLY labels every artifact as "Demo Blockchain". No fake
             network transactions are ever claimed.

The hash is computed from a deterministic integrity payload so that anyone
holding the stored screening record can recompute and verify it later.

Blockchain anchoring provides tamper-EVIDENCE for the screening record only.
It does NOT prove that a document is genuine.
"""
from __future__ import annotations
import json, hashlib, logging, sqlite3, os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("heimdall.blockchain")

DB_PATH = Path(__file__).resolve().parent.parent / "heimdall.db"
NETWORK_NAME = os.getenv("BLOCKCHAIN_NETWORK", "sepolia")
EXPLORER_TX = os.getenv("BLOCKCHAIN_EXPLORER_TX", "https://sepolia.etherscan.io/tx/")

# Decision ↔ uint8 mapping used on-chain
DECISION_CODES = {"PASS": 0, "REVIEW_REQUIRED": 1, "HIGH_RISK": 2}
DECISION_NAMES = {v: k for k, v in DECISION_CODES.items()}
DECISION_NAMES[3] = "UNKNOWN"

# Minimal ABI — interaction only; the contract itself lives in /contracts
CONTRACT_ABI = [
    {
        "type": "function", "name": "registerScreening", "stateMutability": "nonpayable",
        "inputs": [
            {"name": "screeningId", "type": "bytes32"},
            {"name": "resultHash",  "type": "bytes32"},
            {"name": "riskScore",   "type": "uint8"},
            {"name": "decision",    "type": "uint8"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function", "name": "getScreening", "stateMutability": "view",
        "inputs": [{"name": "screeningId", "type": "bytes32"}],
        "outputs": [
            {"name": "resultHash",   "type": "bytes32"},
            {"name": "riskScore",    "type": "uint8"},
            {"name": "decision",     "type": "uint8"},
            {"name": "timestamp",    "type": "uint64"},
            {"name": "registeredBy", "type": "address"},
            {"name": "exists",       "type": "bool"},
        ],
    },
    {
        "type": "function", "name": "verifyHash", "stateMutability": "view",
        "inputs": [
            {"name": "screeningId", "type": "bytes32"},
            {"name": "resultHash",  "type": "bytes32"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


# ── Configuration ─────────────────────────────────────────────────────────────
def _env() -> dict:
    return {
        "rpc_url":        (os.getenv("BLOCKCHAIN_RPC_URL", "") or "").strip(),
        "private_key":    (os.getenv("BLOCKCHAIN_PRIVATE_KEY", "") or "").strip(),
        "contract_address": (os.getenv("CONTRACT_ADDRESS", "") or "").strip(),
    }


def is_configured() -> bool:
    e = _env()
    return bool(e["rpc_url"] and e["private_key"] and e["contract_address"])


def get_mode() -> str:
    return "sepolia" if is_configured() else "demo"


# ── Integrity payload / hash ──────────────────────────────────────────────────
def integrity_payload(result: dict) -> dict:
    """
    Deterministic, PII-free subset of the result used for hashing.
    Only statuses, scores, check names and outcomes — never values.
    """
    val = result.get("validation", {})
    mrz = result.get("mrz", {})
    tamp = result.get("tampering", {})
    face = result.get("face_verification", {})
    risk = result.get("risk", {})
    return {
        "v": 1,  # payload schema version
        "screening_id": result.get("screening_id", ""),
        "timestamp": result.get("timestamp", ""),
        "document_type": result.get("document_type", ""),
        "document_type_confidence": result.get("document_type_confidence", 0),
        "validation": sorted(
            [f"{c.get('check_name','?')}={c.get('status','?')}" for c in val.get("checks", [])]
        ),
        "validation_summary": {
            "passed": val.get("passed", 0),
            "warnings": val.get("warnings", 0),
            "failed": val.get("failed", 0),
        },
        "mrz": {
            "status": mrz.get("status", ""),
            "checks": sorted(
                [f"{c.get('check_name','?')}={c.get('status','?')}" for c in mrz.get("checks", [])]
            ),
        },
        "tampering": {
            "status": tamp.get("status", ""),
            "overall_confidence": tamp.get("overall_confidence", 0),
        },
        "face_verification": {
            "status": face.get("status", ""),
            "match_score": face.get("match_score"),
        },
        "risk": {"score": risk.get("score", 0), "decision": risk.get("decision", "")},
        "demo_mode": bool(result.get("demo_mode", False)),
    }


def compute_result_hash(result: dict) -> str:
    """SHA-256 (hex, 0x-prefixed) of the canonical PII-free integrity payload."""
    canonical = json.dumps(
        integrity_payload(result), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "0x" + hashlib.sha256(canonical).hexdigest()


def _screening_id_bytes32(screening_id: str) -> bytes:
    b = screening_id.encode("ascii")[:32]
    return b.ljust(32, b"\0")


def _bytes32_to_id(b: bytes) -> str:
    return b.rstrip(b"\0").decode("ascii", errors="replace")


# ── Demo ledger (local, clearly labelled) ─────────────────────────────────────
def _demo_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("""CREATE TABLE IF NOT EXISTS blockchain_demo_anchors (
        screening_id  TEXT PRIMARY KEY,
        result_hash   TEXT NOT NULL,
        risk_score    INTEGER NOT NULL,
        decision      INTEGER NOT NULL,
        anchored_at   TEXT NOT NULL,
        prev_hash     TEXT NOT NULL,
        tx_hash       TEXT NOT NULL)""")
    return con


def _demo_register(screening_id: str, result_hash: str, risk_score: int, decision: int) -> dict:
    con = _demo_con()
    try:
        row = con.execute(
            "SELECT prev_hash, tx_hash FROM blockchain_demo_anchors WHERE screening_id=?",
            (screening_id,),
        ).fetchone()
        if row:
            return {
                "status": "ALREADY_REGISTERED",
                "tx_hash": row[1],
                "onchain_hash": None,
            }
        last = con.execute(
            "SELECT tx_hash FROM blockchain_demo_anchors ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        prev = last[0] if last else "0x" + "0" * 64
        material = f"demo-block|{screening_id}|{result_hash}|{prev}|{datetime.now(timezone.utc).isoformat()}"
        tx_hash = "0x" + hashlib.sha256(material.encode()).hexdigest()
        con.execute(
            "INSERT INTO blockchain_demo_anchors (screening_id, result_hash, risk_score, decision,"
            " anchored_at, prev_hash, tx_hash) VALUES (?,?,?,?,?,?,?)",
            (screening_id, result_hash, risk_score, decision,
             datetime.now(timezone.utc).isoformat(), prev, tx_hash),
        )
        con.commit()
        return {"status": "REGISTERED", "tx_hash": tx_hash, "onchain_hash": None}
    finally:
        con.close()


def _demo_verify(screening_id: str, result_hash: str) -> dict:
    con = _demo_con()
    try:
        row = con.execute(
            "SELECT result_hash FROM blockchain_demo_anchors WHERE screening_id=?",
            (screening_id,),
        ).fetchone()
        if not row:
            return {"exists": False, "onchain_hash": None, "verified": False}
        return {
            "exists": True,
            "onchain_hash": row[0],
            "verified": row[0] == result_hash,
        }
    finally:
        con.close()


# ── Real chain (Ethereum-compatible testnet) ──────────────────────────────────
def _w3():
    from web3 import Web3
    e = _env()
    w3 = Web3(Web3.HTTPProvider(e["rpc_url"], request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise ConnectionError("Blockchain RPC is not reachable.")
    return w3


def _chain_register(screening_id: str, result_hash: str, risk_score: int, decision: int) -> dict:
    from web3 import Web3
    from eth_account import Account
    e = _env()
    w3 = _w3()
    acct = Account.from_key(e["private_key"])
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(e["contract_address"]), abi=CONTRACT_ABI
    )
    sid = _screening_id_bytes32(screening_id)
    rh = bytes.fromhex(result_hash[2:])
    tx = contract.functions.registerScreening(
        sid, rh, max(0, min(100, int(risk_score))), int(decision)
    ).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 300_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": w3.eth.chain_id,
    })
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        status = "REGISTERED" if receipt.status == 1 else "FAILED"
        return {
            "status": status,
            "tx_hash": tx_hash.hex(),
            "block_number": receipt.blockNumber,
            "onchain_hash": None,
        }
    except Exception:
        return {"status": "PENDING", "tx_hash": tx_hash.hex(), "block_number": None, "onchain_hash": None}


def _chain_verify(screening_id: str, result_hash: str) -> dict:
    from web3 import Web3
    e = _env()
    w3 = _w3()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(e["contract_address"]), abi=CONTRACT_ABI
    )
    rh = bytes.fromhex(result_hash[2:])
    onchain = contract.functions.getScreening(_screening_id_bytes32(screening_id)).call()
    oc_hash = "0x" + onchain[0].hex()
    exists = bool(onchain[5])
    verified = bool(contract.functions.verifyHash(_screening_id_bytes32(screening_id), rh).call())
    return {"exists": exists, "onchain_hash": oc_hash if exists else None, "verified": verified}


# ── Public API ────────────────────────────────────────────────────────────────
def anchor_result(result: dict) -> dict:
    """
    Compute the integrity hash and anchor it. Returns the evidence object
    stored with the screening record and shown in the UI/report.
    Never raises — failures degrade to an explicit unanchored status.
    """
    screening_id = result.get("screening_id", "")
    risk = result.get("risk", {})
    result_hash = compute_result_hash(result)
    decision_code = DECISION_CODES.get(risk.get("decision", ""), 3)
    mode = get_mode()

    evidence = {
        "mode": mode,
        "network": NETWORK_NAME if mode == "sepolia" else "demo-ledger",
        "network_label": ("Ethereum Sepolia Testnet" if mode == "sepolia"
                          else "Demo Blockchain (local ledger)"),
        "contract_address": (_env()["contract_address"] or None) if mode == "sepolia"
                            else "demo://heimdall.local-ledger",
        "screening_id": screening_id,
        "result_hash": result_hash,
        "risk_score": risk.get("score", 0),
        "decision": risk.get("decision", ""),
        "hash_algorithm": "SHA-256 (canonical integrity payload, PII-free)",
        "status": "FAILED",
        "tx_hash": None,
        "block_number": None,
        "explorer_url": None,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "note": "",
    }

    try:
        if mode == "sepolia":
            r = _chain_register(screening_id, result_hash, risk.get("score", 0), decision_code)
            evidence["status"] = r["status"]
            evidence["tx_hash"] = r["tx_hash"]
            evidence["block_number"] = r.get("block_number")
            evidence["explorer_url"] = EXPLORER_TX + r["tx_hash"] if r.get("tx_hash") else None
            evidence["note"] = ("Anchored on the Ethereum Sepolia testnet. Only the hash, "
                                "screening ID, score and decision are on-chain — no personal data.")
        else:
            r = _demo_register(screening_id, result_hash, risk.get("score", 0), decision_code)
            evidence["status"] = "DEMO_" + r["status"] if r["status"] == "REGISTERED" else "ALREADY_REGISTERED"
            evidence["tx_hash"] = r["tx_hash"]
            evidence["explorer_url"] = None
            evidence["note"] = ("DEMO BLOCKCHAIN — no network transaction was made. The hash was "
                                "recorded in a local tamper-evident ledger for demonstration. "
                                "No personal data is ever stored.")
    except Exception as e:
        logger.error("Blockchain anchoring failed [%s]: %s", screening_id, e)
        evidence["status"] = "FAILED"
        evidence["note"] = f"Anchoring could not be completed: {e}"
    return evidence


def verify_screening(stored_result: dict) -> dict:
    """
    Recompute the hash from the stored screening record and check it against
    the anchored record (on-chain or demo ledger).
    """
    screening_id = stored_result.get("screening_id", "")
    expected = compute_result_hash(stored_result)
    mode = get_mode()
    try:
        if mode == "sepolia":
            r = _chain_verify(screening_id, expected)
        else:
            r = _demo_verify(screening_id, expected)
        if not r.get("exists"):
            verdict, msg = "NOT_FOUND", "No anchored record exists for this screening ID."
        elif r.get("verified"):
            verdict = "VERIFIED"
            msg = ("Integrity verified — the stored screening record is byte-identical "
                   "to the record anchored at registration time.")
        else:
            verdict, msg = "MISMATCH", (
                "Integrity FAILURE — the recomputed hash does not match the anchored hash. "
                "The screening record has been modified after registration."
            )
        return {
            "mode": mode,
            "network": NETWORK_NAME if mode == "sepolia" else "demo-ledger",
            "network_label": ("Ethereum Sepolia Testnet" if mode == "sepolia"
                              else "Demo Blockchain (local ledger)"),
            "screening_id": screening_id,
            "computed_hash": expected,
            "onchain_hash": r.get("onchain_hash"),
            "anchored": r.get("exists", False),
            "verified": bool(r.get("verified")),
            "verdict": verdict,
            "message": msg,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": ("Blockchain verification confirms the screening RECORD has not "
                           "been altered. It does not prove that a document is genuine."),
        }
    except Exception as e:
        logger.error("Blockchain verification failed [%s]: %s", screening_id, e)
        return {
            "mode": mode, "network": mode, "screening_id": screening_id,
            "computed_hash": expected, "onchain_hash": None, "anchored": None,
            "verified": False, "verdict": "UNAVAILABLE",
            "message": f"Verification is currently unavailable: {e}",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": ("Blockchain verification confirms the screening RECORD has not "
                           "been altered. It does not prove that a document is genuine."),
        }
