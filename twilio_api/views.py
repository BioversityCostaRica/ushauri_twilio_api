import arrow
import logging
import os
import uuid
from datetime import datetime, timedelta
from urllib.request import urlretrieve

from pyramid.response import Response, FileResponse
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from ushauri.processes import (
    getItemData,
    getItemResponses,
    getAudioFile,
    storeQuestion,
    isNumberAnAgent,
    isNumberAMember,
    getAgentStartItem,
    getMemberStartItem,
    getMemberAndGroup,
    getAudioFileName,
    recordLog,
)
from ushauri.processes.db.maintenance import getUserDetails, addAudio, setQuestionStatus

log = logging.getLogger(__name__)


def twiml(resp):
    headers = [("Content-Type", "text/xml; charset=utf-8")]
    resp = Response(body=str(resp), headerlist=headers)
    return resp


def send_reply(request, number, audio_id, question_id):
    account_sid = request.registry.settings["twilio.account.sid"]
    auth_token = request.registry.settings["twilio.auth.token"]
    client = Client(account_sid, auth_token)
    client.calls.create(
        to=number,
        from_=request.registry.settings["twilio.number"],
        url=request.route_url("sendreply", audioid=audio_id),
        method="GET",
        status_callback=request.route_url(
            "replystatus", questionid=question_id, audioid=audio_id
        ),
    )


def ivr_send_view(request):
    audio_id = request.matchdict["audioid"]
    response = VoiceResponse()
    response.play(
        request.url_for_static("static/audio/" + getAudioFileName(request, audio_id)),
        loop=0,
    )
    response.hangup()
    return twiml(response)


def ivr_reply_status_view(request):
    if request.method == "POST":
        question_id = request.matchdict["questionid"]
        audio_id = request.matchdict["audioid"]
        print("************************A99")
        call_status = request.POST.get("CallStatus", "failed")
        if call_status == "completed":
            setQuestionStatus(request, question_id, 3, audio_id)
        else:
            setQuestionStatus(request, question_id, -1, audio_id)
        print("************************A99")
    resp = Response()
    return resp


def ivr_voice_start_view(request):
    number = request.params["From"]
    # If the number is malformed like +792490972 then remove the + and add country code
    country_code = request.registry.settings["country.code"]
    if number[: len(country_code)] != country_code:
        print("*****************90")
        print("Fixing" + number)
        print("--------------------------")
        print(request.params)
        print("*****************90")
        number = country_code + number[1:]

    agent = isNumberAnAgent(request, number)
    # agent = None #Only for Skype test. Remove soon

    if agent is not None:
        menu_item = getAgentStartItem(request, agent)
        if menu_item is not None:
            response = VoiceResponse()
            response.redirect(
                request.route_url("ivrget", itemid=menu_item), method="GET"
            )
            return twiml(response)
        else:
            resp = VoiceResponse()
            resp.say("Sorry your account does not have a active menu")
            resp.hangup()
            return twiml(resp)
    else:
        member = isNumberAMember(request, number)

        # member = "2aade9ca2adb" #Only for Skype test. Remove soon

        if member is not None:
            menu_item = getMemberStartItem(request, member)
            if menu_item is not None:
                response = VoiceResponse()
                response.redirect(
                    request.route_url("ivrget", itemid=menu_item), method="GET"
                )
                return twiml(response)
            else:
                resp = VoiceResponse()
                resp.say("Sorry your account does not have a active menu")
                resp.hangup()
                return twiml(resp)
        else:
            resp = VoiceResponse()
            resp.say(
                "Contact your extension agent so he/she register you for this service"
            )
            resp.hangup()
            return twiml(resp)


def ivr_get_view(request):
    item_id = request.matchdict["itemid"]
    item_data = getItemData(request, item_id)
    number = request.params["From"]
    # If the number is malformed like +792490972 then remove the + and add country code
    country_code = request.registry.settings["country.code"]
    if number[: len(country_code)] != country_code:
        print("*****************92")
        print("Fixing" + number)
        print("----------------------------")
        print(request.params)
        print("*****************92")
        number = country_code + number[1:]
    recordLog(request, number, item_id)
    if item_data is not None:
        if request.method == "GET":
            if item_data["item_type"] == 1:
                response = VoiceResponse()
                audio_data = getAudioFile(request, item_id)
                if audio_data is None:
                    with response.gather(
                        numDigits=1,
                        action=request.route_url("ivrpost", itemid=item_id),
                        method="POST",
                    ) as g:
                        g.say(
                            item_data["item_desc"],
                            voice="alice",
                            language="en-GB",
                            loop=3,
                        )
                else:
                    with response.gather(
                        numDigits=1,
                        action=request.route_url("ivrpost", itemid=item_id),
                        method="POST",
                    ) as g:
                        g.play(
                            request.url_for_static(
                                "static/audio/" + audio_data["audio_file"]
                            ),
                            loop=3,
                        )
                return twiml(response)

            if item_data["item_type"] == 2:
                resp = VoiceResponse()
                audio_data = getAudioFile(request, item_id)
                if audio_data is None:
                    resp.say("Record your message after the tone.")
                else:
                    resp.play(
                        request.url_for_static(
                            "static/audio/" + audio_data["audio_file"]
                        ),
                        loop=1,
                    )
                resp.record(
                    maxLength=60,
                    action=request.route_url("ivrstore", itemid=item_id),
                    method="POST",
                    finish_on_key="*",
                )
                resp.hangup()
                return twiml(resp)
            if item_data["item_type"] == 3:
                audio_data = getAudioFile(request, item_id)
                response = VoiceResponse()
                response.play(
                    request.url_for_static("static/audio/" + audio_data["audio_file"]),
                    loop=1,
                )
                if item_data["next_item"] is not None:
                    response.redirect(
                        request.route_url("ivrget", itemid=item_data["next_item"]),
                        method="GET",
                    )
                    return twiml(response)
                else:
                    response.hangup()
                    return twiml(response)
        else:
            resp = VoiceResponse()
            resp.say("Error, you are in the get url but in a post call")
            resp.hangup()
            return twiml(resp)
    else:
        resp = VoiceResponse()
        resp.say("Invalid item")
        resp.hangup()
        return twiml(resp)


def ivr_post_view(request):
    item_id = request.matchdict["itemid"]
    item_data = getItemData(request, item_id)
    if item_data is not None:
        item_responses = getItemResponses(request, item_id)
        if request.method == "POST":
            soption = request.POST.get("Digits", "0")
            try:
                noption = int(soption)
            except Exception as e:
                log.error("ivr_post_view error: {}".format(str(e)))
                resp = VoiceResponse()
                resp.say(
                    "Sorry, you did not typed a number. Redirecting you to the main menu"
                )
                resp.redirect(request.route_url("ivrstart"), method="GET")
                return twiml(resp)
            for resp in item_responses:
                if resp["resp_num"] == noption:
                    response = VoiceResponse()
                    response.redirect(
                        request.route_url("ivrget", itemid=resp["target_item"]),
                        method="GET",
                    )
                    return twiml(response)
            resp = VoiceResponse()
            resp.say("Error, was not able to find a response")
            resp.hangup()
            return twiml(resp)
        else:
            resp = VoiceResponse()
            resp.say("Error, you are in the post url but in a get call")
            resp.hangup()
            return twiml(resp)
    else:
        resp = VoiceResponse()
        resp.say("Invalid item")
        resp.hangup()
        return twiml(resp)


def ivr_store_view(request):
    if request.method == "POST":
        recording_url = request.POST.get("RecordingUrl", None)
        if recording_url is not None:
            uid = str(uuid.uuid4())
            number = request.POST.get(
                "From", ""
            )  # We assume here that the platform made the call. Change to From
            # If the number is malformed like +792490972 then remove the + and add country code
            country_code = request.registry.settings["country.code"]
            if number[: len(country_code)] != country_code:
                print("*****************93")
                print("Fixing" + number)
                print("*****************93")
                number = country_code + number[1:]
            agent = isNumberAnAgent(request, number)

            # agent = None #Only for Skype test. Remove soon

            if agent is not None:
                data = getUserDetails(request, agent)
                path = os.path.join(
                    request.registry.settings["audioPath"], *[uid + ".wav"]
                )
                urlretrieve(recording_url, path)
                ar = arrow.get(datetime.now() + timedelta(hours=3))  # Nairobi time
                addAudio(
                    request,
                    uid,
                    "Audio recorded by agent "
                    + data["user_name"]
                    + " the "
                    + ar.format("Do of MMMM, YYYY - HH:mm:ss"),
                    uid + ".wav",
                    2,
                    data["user_id"],
                )
            else:
                group, member = getMemberAndGroup(request, number)

                # group = "eb3f40b10ca4"
                # member = "2aade9ca2adb"

                path = os.path.join(
                    request.registry.settings["repository"], *[uid + ".wav"]
                )
                urlretrieve(recording_url, path)
                storeQuestion(request, group, member, uid)
            resp = VoiceResponse()
            resp.hangup()
            return twiml(resp)
        else:
            resp = VoiceResponse()
            resp.hangup()
            return twiml(resp)
    else:
        resp = VoiceResponse()
        resp.hangup()
        return twiml(resp)


def ivr_get_audio_view(request):
    item_id = request.matchdict["audioid"]
    response = FileResponse(
        os.path.join(request.registry.settings["repository"], *[item_id + ".wav"]),
        request=request,
        content_type="audio/wav",
    )
    return response
