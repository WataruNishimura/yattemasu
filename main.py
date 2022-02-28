import json
import logging
import os
import config
from database import DataBase
from modules.jwt import getJWTtoken
from fastapi import FastAPI, Request, Response, Header
from firebase_admin import credentials
from firebase_admin import db
import uvicorn
from modules.api import MessagingApi
import base64
import hashlib
import hmac
from pydantic import BaseModel, Json
from models import EventObject, FlexMessageObject,  MessageObject, UserProfile
import googlemaps
from googlemaps import places

messaging_api_url = "https://api.line.me/oauth2/v2.1"
messaging_api = MessagingApi("")

mode = os.getenv("MODE") if os.getenv("MODE") else "development"
channel_secret = os.getenv("CLIENT_SECRET")
app = FastAPI()
gmaps_api_key = os.getenv("gmaps_api_key")

shop_card_json = open("components/shop_card.json", mode="rt", encoding="utf-8")
class WebhookData(BaseModel):
    destination: str
    events: list


@app.on_event("startup")
async def startup():
    logger = logging.getLogger("uvicorn")
    jwt = getJWTtoken(".")

    print(f"JWT is {type(jwt)}")

    database = DataBase(
        credentialsFile="credentials.json",
        databaseURL=
        "https://darts-chatbot-example-default-rtdb.asia-southeast1.firebasedatabase.app/"
    )

    messaging_api.setAccessToken(access_token=database.getChannelAccessToken(
        jwt=jwt))


async def webhook_handler(request: Request, response: Response,
                          x_line_signature, webhook_input: WebhookData):
    body = await request.body()
    body = body.decode("utf-8")
    destination = webhook_input.destination
    gmaps = googlemaps.Client(key=gmaps_api_key)
    events = webhook_input.events
    logger = logging.getLogger("uvicorn")
    if (events == []):
        if (x_line_signature): # LINE Messaging API の署名確認
            hash = hmac.new(channel_secret.encode("utf-8"),
                            body.encode("utf-8"), hashlib.sha256).digest()
            signature = base64.b64encode(hash)
            if (signature.decode("utf-8") == x_line_signature):
                logger.info("LINE Sinature is valid.")
                return
            else:
                logger.error("Invalid message signature")
                response.status_code = 400
                return
        response.status_code = 403
        logger.error("No x-line-sinature spcified.")
        return

    for event in events:
        event = EventObject.parse_obj(event)
        if (event.type == "message"):
            if (event.message.type == "text"):

                logger.info(event.message.text)
                profile: UserProfile = messaging_api.getUserProfile(
                    event.source.userId)

                shops = places.find_place(input=event.message.text, input_type="textquery", client=gmaps, language="ja_JP")
                shop_is_open = False
                searched_shop_list = []
                for shop in shops["candidates"]:
                    place_id = shop["place_id"]
                    shop_data = places.place(gmaps, place_id=place_id, language="ja_JP", fields=["opening_hours", "photo", "website", "name", "formatted_address", "url"])
                    searched_shop_list.append(shop_data["result"])
                
                text = "そのお店、やってません"
                if(searched_shop_list[0]["opening_hours"]["open_now"]):
                    text = "そのお店、やってます"

                logger.info(searched_shop_list[0])
                
                shop_card_dictionary = json.load(shop_card_json)
                shop_card_dictionary["body"]["contents"][0]["contents"][0]["text"] = text
                shop_card_dictionary["body"]["contents"][1]["text"] = searched_shop_list[0]["name"]
                shop_card_dictionary["body"]["contents"][3]["contents"][0]["contents"][1]["text"] = searched_shop_list[0]["formatted_address"]
                shop_card_dictionary["footer"]["contents"][0]["action"]["uri"] = searched_shop_list[0]["url"]
                shop_card_dictionary["footer"]["contents"][1]["action"]["uri"] = searched_shop_list[0]["website"]
                shop_card_dictionary["hero"]["url"] = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={searched_shop_list[0]['photos'][0]['width']}&photoreference={searched_shop_list[0]['photos'][0]['photo_reference']}&sensor=false&key={gmaps_api_key}"

                replyMessages = [
                    FlexMessageObject(type="flex", altText="Flex Message", contents=shop_card_dictionary).dict()
                ]
                messaging_api.replyMessage(replyToken=event.replyToken,
                                           messages=replyMessages)
            elif (event.message.type == "image"):
                profile: UserProfile = messaging_api.getUserProfile(
                    event.source.userId)
                replyMessages = [
                    MessageObject(
                        type="text",
                        text=f"{profile.displayName} さんその画像いいですね").dict()
                ]
                messaging_api.replyMessage(replyToken=event.replyToken,
                                           messages=replyMessages)
        elif (event.type == "follow"):
            logger.info(messaging_api.getAccessToken())
            profile: UserProfile = messaging_api.getUserProfile(
                event.source.userId)
            logger.info(profile.displayName)
            replyMessages = [
                MessageObject(type="text",
                              text=f"{profile.displayName} さんこんにちは。").dict()
            ]
            messaging_api.replyMessage(replyToken=event.replyToken,
                                       messages=replyMessages)



@app.post("/webhook", status_code=200)
async def webhook(
        webhook_input: WebhookData,
        request: Request,
        response: Response,
        content_length: int = Header(...),
        x_line_signature: str = Header("x-ling-signature"),
):
    await webhook_handler(request=request,
                          response=response,
                          x_line_signature=x_line_signature,
                          webhook_input=webhook_input)
    return


if __name__ == "__main__":

    reload = True if (mode == "development") else False

    uvicorn.run("main:app",
                host="127.0.0.1",
                port=8080,
                log_level="info",
                reload=True)
