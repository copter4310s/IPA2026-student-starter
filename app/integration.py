"""Part 4 student implementation."""

from app.core import load_request_data, validate_request
from app.dispatcher import dispatch_request
from app.request_handler import validate_webex_envelope

def process_request(mentioned_people, attachment_path, bot_person_id):
    envelope_error = validate_webex_envelope(
        mentioned_people, attachment_path, bot_person_id
    )
    if envelope_error is not None:
        return envelope_error

    request_data, parse_error = load_request_data(attachment_path)
    if parse_error is not None:
        return parse_error
    validation_error = validate_request(request_data)
    if validation_error is not True:
        return validation_error
    return dispatch_request(request_data)
