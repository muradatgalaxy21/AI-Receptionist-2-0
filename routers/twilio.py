# routers/twilio.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.post("/incoming-call")
async def incoming_call(request: Request):
    """
    Engineer A Task:
    1. Receive call from Twilio.
    2. Respond with XML instructions.
    3. Tell Twilio to connect to the 'media-stream' (managed by Ahad).
    """
    host = request.headers.get('host')
    
    response_xml = f"""
    <Response>
        <Say>Connecting you to the AI Receptionist.</Say>
        <Connect>
            <Stream url="wss://{host}/media-stream" />
        </Connect>
    </Response>
    """
    return HTMLResponse(content=response_xml, media_type="application/xml")