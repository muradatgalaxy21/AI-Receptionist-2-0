from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.post("/incoming-call")
async def incoming_call(request: Request):
    host = request.headers.get("host")
    ws_url = f"wss://{host}/media-stream"

    print(f"\nINCOMING CALL DETECTED!")
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
