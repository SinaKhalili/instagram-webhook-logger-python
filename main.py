from fastapi import FastAPI, Request, Response, HTTPException, Query
from fastapi.responses import JSONResponse
import hmac
import hashlib
from typing import Optional
import json
import os
from datetime import datetime
import uvicorn
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

APP_SECRET = os.getenv("APP_SECRET")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
INSTAGRAM_API_URL = "https://graph.instagram.com/v12.0"

received_updates = []

def save_update_to_file(update: dict, filename: str = "webhook_updates.jsonl"):
    """
    Append the update as a JSON string to the specified file.
    Each line in the file will represent one JSON object.
    """
    try:
        with open(filename, "a") as f:
            f.write(json.dumps(update) + "\n")
    except Exception as e:
        print(f"Error saving update to file: {e}")

def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verify that the payload was sent from Instagram"""
    if not signature_header:
        return False
    
    expected_signature = hmac.new(
        bytes(APP_SECRET, 'utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected_signature}", signature_header)

@app.get("/")
async def root(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    print(f"Received request: {hub_mode}, {hub_verify_token}, {hub_challenge}")
    """Handle both displaying updates and webhook verification"""
    if hub_mode is not None:
        print("Verification Details:")
        print(f"- Received mode: {hub_mode}")
        print(f"- Received token: {hub_verify_token}")
        print(f"- Expected token: {VERIFY_TOKEN}")
        print(f"- Received challenge: {hub_challenge}")
        
        if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
            print("Verification successful!")
            return Response(content=hub_challenge)
        else:
            print("Verification failed - token mismatch")
            raise HTTPException(status_code=400, detail="Invalid verification request")
    
    return JSONResponse({"message": "ok"})

@app.post("/")
async def instagram_webhook(request: Request):
    """Handle webhook events from Instagram"""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    
    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    print(f"Received webhook: {json.dumps(payload, indent=2)}")
    
    # Create update record with timestamp and payload
    update = {
        "timestamp": datetime.now().isoformat(),
        "payload": payload
    }
    
    # Store update in memory
    received_updates.insert(0, update)
    
    # Save update to file
    save_update_to_file(update)
    
    return Response(status_code=200)

@app.post("/setup_webhooks")
async def setup_webhook_subscriptions():
    """Enable webhook subscriptions for the app"""
    if not ACCESS_TOKEN:
        raise HTTPException(status_code=400, detail="Access token not configured")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{INSTAGRAM_API_URL}/me/subscribed_apps",
                params={
                    "subscribed_fields": "comments,messages,story_insights",
                    "access_token": ACCESS_TOKEN
                }
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to setup webhooks: {str(e)}")

if __name__ == "__main__":
    print("Starting webhook server...")
    print("Make sure to set these environment variables:")
    print("- APP_SECRET: Your Instagram app secret")
    print("- VERIFY_TOKEN: Your webhook verification token")
    print("- ACCESS_TOKEN: Your Instagram access token")
    uvicorn.run(app, host="0.0.0.0", port=8000)
