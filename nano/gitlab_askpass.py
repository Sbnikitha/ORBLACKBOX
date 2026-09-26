"""Print a GitLab username or project token for one git command. Do not commit the token."""
import sys
from pathlib import Path

SECRET = Path.home() / ".or-sentinel" / "gitlab-token"
prompt = " ".join(sys.argv[1:]).lower()
if "username" in prompt:
    print("oauth2")
else:
    print(SECRET.read_text(encoding="utf-8").strip())
