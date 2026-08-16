# Mini VPS Panel (Vercel)

Ek chhota web-based VPS jaisa panel — Railway pe deploy hota hai. Owner users banata hai, har user apni Python / Node / Shell files upload, run, restart, stop kar sakta hai, modules install kar sakta hai, aur real-time logs dekh sakta hai.

## Owner credentials
- Username: `*******`
- Password: `***********`

## Deploy on Render

1. Is `vps-panel/` folder ko ek naye GitHub repo ki **root** me push karo.
2. Vercel → New Project → Deploy from GitHub repo → repo select karo.
3. Vercel automatically `nixpacks.toml` se Python 3.11 + Node 20 install karega aur `Procfile` se gunicorn start karega.
4. Settings → Networking → **Generate Domain**.
5. Domain pe jao, `dark / dark_codex` se login karo.

## Features

**Owner:**
- Naye users banao (username, password, expiry hours)
- Har user ka **auto-login link** milta hai (share karne ke liye)
- Users ko extend / delete karo
- Expiry hone par user auto-delete + uska process auto-stop

**User:**
- Multiple files ek saath upload (200MB tak)
- `.py` / `.js` / `.sh` files ko Start / Stop / Restart
- Real-time logs (auto-refresh)
- Modules install: `pip install <module>` ya `npm install <module>`
- File view aur delete

## Notes

- Vercel ke ephemeral filesystem ki wajah se redeploy hone par uploaded files / users.json reset ho sakte hain. Persist karne ke liye Railway Volume mount karo `/app/vps-panel/data` aur `/app/vps-panel/user_files` pe.
- `SECRET_KEY` env var set karo production me (warna har restart pe sessions reset ho jate hain).
- Sirf `pip install` / `npm install` commands allowed hain (security).

## Local run

```bash
cd vps-panel
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```
