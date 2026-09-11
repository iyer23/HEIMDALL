"""
HEIMDALL — Blockchain Evidence Router (additive)
Endpoints for inspecting the blockchain anchor of a screening record and
verifying its integrity. Does NOT touch the screening pipeline logic.
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from database.db import get_db
from models.screening import ScreeningRecord
from services import blockchain_service as bcs

router = APIRouter(prefix="/api/blockchain", tags=["blockchain"])
logger = logging.getLogger("heimdall.blockchain_router")


@router.get("/status")
async def status():
    mode = bcs.get_mode()
    return {
        "mode": mode,
        "network": bcs.NETWORK_NAME if mode == "sepolia" else "demo-ledger",
        "network_label": ("Ethereum Sepolia Testnet" if mode == "sepolia"
                          else "Demo Blockchain (local ledger)"),
        "contract_address": bcs._env()["contract_address"] or None,
        "configured": bcs.is_configured(),
        "note": ("Real anchoring is active." if mode == "sepolia" else
                 "Blockchain env vars not configured — running in DEMO mode "
                 "(local tamper-evident ledger, clearly labelled)."),
    }


@router.get("/{screening_id}")
async def evidence(screening_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(ScreeningRecord, screening_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Screening not found")
    data = rec.get_result() or {}
    ev = data.get("blockchain")
    if not ev:
        # Anchored before this feature existed, or anchoring failed: expose
        # the recomputable hash without inventing a transaction.
        ev = {
            "mode": bcs.get_mode(),
            "network_label": ("Ethereum Sepolia Testnet" if bcs.is_configured()
                              else "Demo Blockchain (local ledger)"),
            "screening_id": screening_id,
            "result_hash": bcs.compute_result_hash(data) if data else None,
            "status": "NOT_ANCHORED",
            "tx_hash": None,
            "note": "This record was not anchored (created before the blockchain "
                    "evidence layer, or anchoring failed).",
        }
    return ev


@router.post("/{screening_id}/verify")
async def verify(screening_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(ScreeningRecord, screening_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Screening not found")
    data = rec.get_result()
    if not data:
        raise HTTPException(status_code=404, detail="Result data not found")
    return bcs.verify_screening(data)
