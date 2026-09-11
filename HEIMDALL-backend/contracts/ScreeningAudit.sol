// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * HEIMDALL — ScreeningAudit
 * Tamper-evident anchoring of identity-screening results.
 *
 * PRIVACY: Only non-reversible integrity commitments are stored on-chain:
 *   - a bytes32 screening identifier (opaque code, e.g. "HM-1A2B3C4D5E6F")
 *   - a SHA-256 hash of the screening result's integrity fields
 *   - the numeric risk score and decision code
 *   - a timestamp
 *
 * NEVER store on-chain: passport/ID images, OCR text, names, dates of birth,
 * addresses, document numbers, or any other personal data.
 *
 * NOTE: Anchoring proves the screening RECORD has not been altered since
 * registration. It does NOT prove that a document is genuine.
 */
contract ScreeningAudit {
    struct Record {
        bytes32 resultHash;      // keccak-safe storage of the SHA-256 result hash
        uint8   riskScore;       // 0-100
        uint8   decision;        // 0=PASS 1=REVIEW_REQUIRED 2=HIGH_RISK 3=UNKNOWN
        uint64  timestamp;       // unix seconds of registration
        address registeredBy;    // account that anchored the record
        bool    exists;
    }

    mapping(bytes32 => Record) private records;
    address public admin;

    event ScreeningRegistered(
        bytes32 indexed screeningId,
        bytes32 resultHash,
        uint8   riskScore,
        uint8   decision,
        uint64  timestamp,
        address indexed registeredBy
    );

    constructor() {
        admin = msg.sender;
    }

    /**
     * Anchor a screening result. Reverts if the screening ID was already
     * registered (records are immutable once written).
     */
    function registerScreening(
        bytes32 screeningId,
        bytes32 resultHash,
        uint8   riskScore,
        uint8   decision
    ) external returns (bool) {
        require(!records[screeningId].exists, "Screening already registered");
        require(resultHash != bytes32(0), "Empty hash");
        records[screeningId] = Record({
            resultHash:   resultHash,
            riskScore:    riskScore,
            decision:     decision,
            timestamp:    uint64(block.timestamp),
            registeredBy: msg.sender,
            exists:       true
        });
        emit ScreeningRegistered(
            screeningId, resultHash, riskScore, decision,
            uint64(block.timestamp), msg.sender
        );
        return true;
    }

    /**
     * Fetch the anchored record for a screening ID.
     * exists == false means the ID is unknown on this contract.
     */
    function getScreening(bytes32 screeningId)
        external
        view
        returns (
            bytes32 resultHash,
            uint8   riskScore,
            uint8   decision,
            uint64  timestamp,
            address registeredBy,
            bool    exists
        )
    {
        Record memory r = records[screeningId];
        return (r.resultHash, r.riskScore, r.decision, r.timestamp, r.registeredBy, r.exists);
    }

    /**
     * Pure verification: does the given hash match the anchored record?
     */
    function verifyHash(bytes32 screeningId, bytes32 resultHash)
        external
        view
        returns (bool)
    {
        return records[screeningId].exists && records[screeningId].resultHash == resultHash;
    }
}
