import ushauri.plugins as plugins
import ushauri.plugins.utilities as u
from .views import (
    ivr_get_view,
    ivr_post_view,
    ivr_store_view,
    ivr_get_audio_view,
    ivr_send_view,
    ivr_voice_start_view,
    ivr_reply_status_view,
)
from twilio.rest import Client


class TwilioAPI(plugins.SingletonPlugin):
    plugins.implements(plugins.IRoutes)
    plugins.implements(plugins.IIVR)

    def before_mapping(self, config):
        # We don't add any routes before the host application
        return []

    def after_mapping(self, config):
        # We add here a new route /json that returns a JSON
        custom_map = [
            u.addRoute("ivrget", "/ivrget/{itemid}", ivr_get_view, None),
            u.addRoute("ivrpost", "/ivrpost/{itemid}", ivr_post_view, None),
            u.addRoute("ivrstore", "/ivr/{itemid}/store", ivr_store_view, None),
            u.addRoute("getaudio", "/ivr/{audioid}/play", ivr_get_audio_view, None),
            u.addRoute("sendreply", "/send/{audioid}", ivr_send_view, None),
            u.addRoute("ivrstart", "/start", ivr_voice_start_view, None),
            u.addRoute(
                "replystatus",
                "/replystatus/{questionid}/{audioid}",
                ivr_reply_status_view,
                None,
            ),
        ]
        return custom_map

    def send_reply(self, request, number, audio_id, question_id):
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
