# routers/twilio.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.post("/incoming-call")
async def incoming_call(request: Request):
    # 1. Twilio knocks here when the phone rings
    host = request.headers.get('host')
    
    # 2. We hand Twilio a script (XML) telling it to connect audio to us
    response_xml = f"""
    <Response>
        <Say>This is the AI Receptionist. Connecting you to the AI Receptionist. Your call is important to us. Any questions?</Say>
        <Connect>
            <Stream url="wss://{host}/media-stream" />
        </Connect>
    </Response>
    """
    return HTMLResponse(content=response_xml, media_type="application/xml")