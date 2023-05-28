from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from agent import create_homedepot_agent
from flask import Flask, request, make_response

import os

from dotenv import load_dotenv
load_dotenv()


slack_token = os.environ.get("SLACK_BOT_TOKEN")
slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")

app = App(token=slack_token, signing_secret=slack_signing_secret)
req_url = "https://6eb0-98-216-177-60.ngrok-free.app/slack/events"

@app.message('hello')
def respond_to_hello(message, say):
    say("Hello!")


@app.message()
def respond_to_message(message, say):
    say("Thank you for your question, one moment.")
    text = message.get('text')
    response = helper_agent.run(text)
    say(response)


flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    if "challenge" in request.json:
        return make_response(request.json["challenge"], 200, {"content_type": "application/json"})
    return handler.handle(request)

helper_agent = create_homedepot_agent()
if __name__ == "__main__":
    app.start(port=int(os.environ.get("PORT", 3000)))
    
