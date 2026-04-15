# Douyin-Huohua-WDS-Huiyou

This is a Douyin (TikTok) automation script for sending messages.

## Files

- `main.py` - Main script for sending Douyin messages
- `message_styles.py` - Message styling utilities
- `douyin_cookies.json` - Authentication cookies (not included in git)
- `.github/workflows/main.yml` - GitHub Actions workflow

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Add your Douyin cookies to `douyin_cookies.json` (this file is gitignored for security)

3. Run the script:
```bash
python main.py
```

## Security Note

The `douyin_cookies.json` file contains sensitive authentication data and is intentionally excluded from version control via `.gitignore`. Never commit this file to any repository.