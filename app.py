# app.py
import time
import requests
import base64
from flask import Flask, request, jsonify

app = Flask(__name__)

from flask_cors import CORS
CORS(app)

# endpoints
HORDE_API = "https://stablehorde.net/api/v2/generate/async"
HORDE_STATUS = "https://stablehorde.net/api/v2/generate/status/"  # note : /status/{id}
HORDE_MODELS = "https://stablehorde.net/api/v2/status/models"

# API key: si tu n'as pas de clé, on utilise la clé anonyme "0000000000"
HORDE_API_KEY = None  # ou mets ta clé ici comme "abcd-...."

def _headers():
    return {
        "Content-Type": "application/json",
        "apikey": HORDE_API_KEY or "0000000000",
        "Client-Agent": "decor-proto/1.0"
    }

def call_stable_horde(prompt, width=512, height=512, steps=20, n=1):
    payload = {
        "prompt": prompt,
        "params": {
            "n": n,
            "width": width,
            "height": height,
            "steps": steps,
            "sampler_name": "k_euler"
        },
        "nsfw": False,
        "r2": True
    }

    headers = _headers()
    print("➡️ Payload envoyé:", payload)
    r = requests.post(HORDE_API, json=payload, headers=headers, timeout=30)
    print("➡️ StableHorde HTTP status:", r.status_code)
    print("➡️ StableHorde response body:", r.text[:500])
    if r.status_code not in (200, 201, 202):
        r.raise_for_status()
    return r.json()

def check_horde_result(job_id):
    headers = _headers()
    url = HORDE_STATUS + str(job_id)
    r = requests.get(url, headers=headers, timeout=30)
    print(f"➡️ check_horde_result ({job_id}) status {r.status_code}")
    print("➡️ check_horde_result body:", r.text[:500])
    r.raise_for_status()
    return r.json()

@app.route("/api/decor", methods=["POST"])
def decorate():
    if 'photo' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    style = request.form.get("style", "moderne")

    prompt = f"Interior design styled as {style}, photorealistic, high quality, cozy, well lit"
    print("Prompt envoyé:", prompt)

    try:
        job = call_stable_horde(prompt)
        job_id = job.get("id") or job.get("request_id") or job.get("request") or job.get("job_id")
        if not job_id:
            return jsonify({"error": "Pas d'ID de job renvoyé", "raw_response": job}), 500

        # poller le statut
        last_status = None
        for i in range(40):  # ~ 80s max
            time.sleep(2)
            status = check_horde_result(job_id)
            last_status = status
            if status.get("done") or status.get("generations"):
                gens = status.get("generations") or []
                if len(gens) > 0 and gens[0].get("img"):
                    print("✅ Image trouvée !")
                    img_url = gens[0]['img']

                    # télécharger et convertir en base64
                    resp = requests.get(img_url)
                    resp.raise_for_status()
                    img_base64 = base64.b64encode(resp.content).decode("utf-8")

                    return jsonify({
                        "style": style,
                        "image": img_base64,
                        "status": "ok"
                    })
        return jsonify({"error": "Timeout: pas d'image générée", "last_status": last_status}), 500

    except requests.exceptions.HTTPError as he:
        response = getattr(he, "response", None)
        body = response.text if response is not None else str(he)
        print("Erreur HTTP lors de l'appel à Horde:", he, "body:", body[:500])
        return jsonify({"error": "HTTPError from Horde", "detail": body}), 500
    except Exception as e:
        print("Erreur backend non-HTTP:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/horde/models", methods=["GET"])
def list_models():
    headers = _headers()
    try:
        r = requests.get(HORDE_MODELS, headers=headers, timeout=15)
        print("Models status:", r.status_code)
        print("Models body:", r.text[:500])
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        print("Erreur list_models:", e)
        return jsonify({"error": str(e), "raw": r.text if 'r' in locals() else None}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
