from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.post("/incoming-call")
async def incoming_call(request: Request):
    host = request.headers.get("host")
    
    # Extract caller number and dialed number from Twilio's form data
    form_data = await request.form()
    caller_id = form_data.get("From", "unknown")
    to_number = form_data.get("To", "unknown")
    
    ws_url = f"wss://{host}/media-stream?caller_id={caller_id}&to_number={to_number}"

    print(f"\nINCOMING CALL DETECTED from {caller_id} to {to_number}!")
    print(f"Telling Twilio to connect to: {ws_url}")
    print(f"--------------------------------------------\n")

    # No <Pause> after <Connect> — when our WebSocket closes, Twilio hangs up immediately.
    response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
    return HTMLResponse(content=response_xml, media_type="application/xml")
