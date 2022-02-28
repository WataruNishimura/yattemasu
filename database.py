import os
from tokenize import String
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import sqlalchemy
from sqlalchemy import Column, Integer

from modules.api import getValidChannelAccessToken, issueChannelAccessToken, verifyChannelAccessToken

Base = sqlalchemy.declarative_base()


class bot_account(Base):
    __tablename__ = "bot_account"
    client_id = Column(Integer, primary_key=True )
    client_secret = Column(String)

class channel_access_token_table(Base):
    __tablename__ = "channel_access_token"
    key_id = Column(Integer, primary_key=True)
    token = Column(String)
    client_id = Column(String)

class bot_user_relation(Base):
    __tablename__ = "bot_user_relation"
class user_account(Base):
    __tablename__ = "user_account"


class Singleton(object):

    def __new__(cls, *args, **kargs):
        if not hasattr(cls, "_instance"):
            cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance


class MysqlDatabase(Singleton):

    def __init__(self, databaseURL, user, password):
        self.engine = sqlalchemy.create_engine(databaseURL, echo=True)


class FirebaseDataBase(Singleton):

    def __init__(self, credentialsFile, databaseURL):
        """In constructor, initialize firebase realtime database.

        Args:
            credentialsFile (str): credentials.json file of Google Firebase Authenication location 
            databaseURL (str): Realtime Database Url
        """
        self.credentials = credentials.Certificate(credentialsFile)
        self.database_url = databaseURL
        self.access_token = ""
        firebase_admin.initialize_app(
            credential=self.credentials,
            options={"databaseURL": self.database_url})
        self.mode = os.getenv("MODE") if os.getenv("MODE") else "development"

    def getChannelAccessToken(self, jwt: str) -> str:
        """ Get Channel Access Token from database. If valid channel access token does not exist in database, retrive it from API.

    Args:
        jwt (str): JSON Web Token

    Returns:
        str: Return valid channel access token.
    """
        kids = getValidChannelAccessToken(jwt=jwt)
        mode = self.mode
        if (len(kids) == 0):
            token_dictionary = issueChannelAccessToken(jwt=jwt)
            ref = db.reference("/line/tokens" + token_dictionary["key_id"])
            ref.set(token_dictionary["access_token"])
            self.access_token = token_dictionary["access_token"]
        else:
            for index in range(len(kids)):
                kid = kids[index]
                ref = db.reference("line/tokens/" + kid)
                kid_token = ref.get()
                if (kid_token != None):
                    if (verifyChannelAccessToken(kid_token)):
                        if (mode == "development"):
                            print("Retrieved token is valid")
                        self.access_token = kid_token
                        break
                    else:
                        if (mode == "development"):
                            print("Retrieved token is expired")
                        ref.delete()
                        token_dictionary = issueChannelAccessToken(jwt=jwt)
                        ref = db.reference("line/tokens/" +
                                           token_dictionary["key_id"])
                        ref.set(token_dictionary["access_token"])
                        self.access_token = token_dictionary["access_token"]
                        break

            if (self.access_token == ""):
                if (mode == "development"):
                    print(
                        "valid token exists, but no valid token is in database"
                    )
                token_dictionary = issueChannelAccessToken(jwt=jwt)
                ref = db.reference("line/tokens/" + token_dictionary["key_id"])
                ref.set(token_dictionary["access_token"])
                self.access_token = token_dictionary["access_token"]

        return self.access_token

    def setChannelAccessToken(self, access_token):
        self.access_token = access_token
