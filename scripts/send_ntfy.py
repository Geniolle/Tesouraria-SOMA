import os
import sys
import urllib.request
import urllib.error

def load_env(env_path="/etc/appextrato/ntfy.env"):
    env = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("\x27\x22")
    return env

def send_ntfy(title: str, message: str, priority: str = "default", tags: list = None, env_path: str = "/etc/appextrato/ntfy.env") -> bool:
    env = load_env(env_path)
    server = env.get("NTFY_SERVER", os.getenv("NTFY_SERVER", "https://ntfy.sh")).rstrip("/")
    topic = env.get("NTFY_TOPIC", os.getenv("NTFY_TOPIC", ""))
    
    if not topic:
        print("Error: NTFY_TOPIC not defined", file=sys.stderr)
        return False

    url = f"{server}/{topic}"
    headers = {
        "Title": title.encode("utf-8").decode("latin-1", errors="replace"),
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)

    token = env.get("NTFY_TOKEN", os.getenv("NTFY_TOKEN", ""))
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 201)
    except Exception as e:
        print(f"Error sending ntfy notification: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        title = "🧪 AppExtrato — TESTE DE MONITORIZAÇÃO"
        message = "Servidor: servidor-tesouraria-v2\nStatus: Teste de conectividade ntfy executado com sucesso."
        tags = ["test", "robot"]
        success = send_ntfy(title, message, priority="default", tags=tags)
        if success:
            print("Test notification sent successfully.")
            sys.exit(0)
        else:
            print("Failed to send test notification.")
            sys.exit(1)
