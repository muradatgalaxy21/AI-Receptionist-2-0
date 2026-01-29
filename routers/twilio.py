from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.post("/incoming-call")
async def incoming_call(request: Request):
    # 1. Get the domain (This MUST be your ngrok URL, not localhost)
    host = request.headers.get('host')
    
    # DEBUG PRINT: Check what URL we are generating
    ws_url = f"wss://{host}/media-stream"
    print(f"\INCOMING CALL DETECTED!")
    print(f"INSTRUCTION: Telling Twilio to connect to:")
    print(f"{ws_url}")
    print(f"--------------------------------------------\n")

    # 2. The improved XML (Includes PAUSE)
    response_xml = f"""
    <Response>
        <Say>This is the AI Receptionist. Connecting you now.</Say>
        <Connect>
            <Stream url="{ws_url}" />
        </Connect>
        <Pause length="20" />
    </Response>
    """
    return HTMLResponse(content=response_xml, media_type="application/xml")