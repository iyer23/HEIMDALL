# ScreeningAudit.sol — Deployment Guide

The backend interacts with this contract via `web3.py` using the minimal ABI
embedded in `services/blockchain_service.py`. To enable REAL anchoring:

1. **Deploy the contract** (easiest: Remix):
   - Open https://remix.ethereum.org → paste `ScreeningAudit.sol` → compile (0.8.x)
   - Deploy via **Injected Provider** (MetaMask) or Remix VM → **Sepolia** requires
     test ETH from a faucet (e.g. sepoliafaucet.com) for gas.
   - Or deploy from the backend venv:
     ```powershell
     # one-time
     uv pip install --python .venv\Scripts\python.exe py-solc-x
     .venv\Scripts\python.exe -c "import solcx; solcx.install_solc('0.8.20')"
     ```
     then deploy with a short script using `web3.eth.contract(abi, bytecode)`.

2. **Configure** `trustscan-backend/.env`:
   ```
   BLOCKCHAIN_RPC_URL=https://sepolia.infura.io/v3/<PROJECT_ID>   # or any Sepolia RPC
   BLOCKCHAIN_PRIVATE_KEY=<deployer-private-key>                  # funded with Sepolia ETH
   CONTRACT_ADDRESS=0x<deployed-address>
   BLOCKCHAIN_NETWORK=sepolia
   ```

3. **Restart the backend.** `GET /api/blockchain/status` must now report
   `mode: "sepolia"` and `configured: true`.

Security notes:
- `BLOCKCHAIN_PRIVATE_KEY` must stay server-side only (`.env`, git-ignored).
  It is never sent to the frontend.
- Only hash / screening ID / score / decision / timestamp are ever on-chain.
- Without configuration the system stays in **Demo Blockchain** mode and
  clearly labels it — no fake transactions are ever claimed.
