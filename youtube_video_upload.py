import logging
import json
import http.client
import httplib2
import os
import random
import time
import json
import sys
import googleapiclient.discovery
import requests
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from urllib.request import urlretrieve
from oauth2client.tools import argparser, run_flow
import google.oauth2.credentials
log = logging.getLogger(__name__)


CLIENT_SECRETS_FILE = 'client_secrets.json'
MISSING_CLIENT_SECRETS_MESSAGE = ""
YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
YOUTUBE_PARTNER = "https://www.googleapis.com/auth/youtubepartner"
YOUTUBE_PARTNER_CONTENT_OWNER = "https://www.googleapis.com/auth/youtubepartner-content-owner-readonly"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_CONTENT_ID_API_SERVICE_NAME = "youtubePartner"
YOUTUBE_CONTENT_ID_API_VERSION = "v1"
MAX_RETRIES = 3
pwd = os.path.dirname(os.path.abspath(__file__))

INVALID_CREDENTIALS = "Invalid Credentials"
CACHED_CREDENTIALS_FILE = "%s-oauth2.json" % sys.argv[0]

YOUTUBE_SCOPES = (
    # An OAuth 2 access scope that allows for full read/write access.
    "https://www.googleapis.com/auth/youtube",
    # A scope that grants access to YouTube Partner API functionality.
    "https://www.googleapis.com/auth/youtubepartner",
    # A scope that grants access to content owner ID's for monetization
    "https://www.googleapis.com/auth/youtubepartner-content-owner-readonly")


VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, http.client.NotConnected,
  http.client.IncompleteRead, http.client.ImproperConnectionState,
  http.client.CannotSendRequest, http.client.CannotSendHeader,
  http.client.ResponseNotReady, http.client.BadStatusLine)

class YoutubeUpload():
    CLIENT_SECRETS_FILE = 'YOUR CLIENT SECRET'
    VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


    def get_credentials(self, client_secret_file):
        with open(pwd + '/' + client_secret_file, 'r') as f:
            json_ = json.load(f)
        json_file = json_['web']
        client_secret_json = {
            'token_uri': json_file['token_uri'],
            'client_id': json_file['client_id'],
            'client_secret': json_file['client_secret'],
            'scopes': " ".join(YOUTUBE_SCOPES)
        }

        return client_secret_json

    def get_authenticated_service(self, client_secret_json):
        # print(client_secret_json)
        credentials = google.oauth2.credentials.Credentials(
            **client_secret_json)
        print(credentials)
        client = googleapiclient.discovery.build(
            YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials, cache_discovery=False)

        youtube_partner = googleapiclient.discovery.build(YOUTUBE_CONTENT_ID_API_SERVICE_NAME, YOUTUBE_CONTENT_ID_API_VERSION, credentials=credentials, cache_discovery=False)

        return client, youtube_partner

    def initialize_upload(self, youtube, options):
        print("initialize upload")
        tags = None
        if options.keywords:
            tags = options.keywords.split(",")

        body = dict(
            snippet=dict(
                title=options.title,
                description=options.description,
                tags=tags,
                categoryId=options.category
            ),
            status=dict(
                privacyStatus=options.privacyStatus
            )
        )

        # Call the API's videos.insert method to create and upload the video.
        insert_request = youtube.videos().insert(
            part=",".join(list(body.keys())),
            body=body,
            # The chunksize parameter specifies the size of each chunk of data, in
            # bytes, that will be uploaded at a time. Set a higher value for
            # reliable connections as fewer chunks lead to faster uploads. Set a lower
            # value for better recovery on less reliable connections.
            #
            # Setting "chunksize" equal to -1 in the code below means that the entire
            # file will be uploaded in a single HTTP request. (If the upload fails,
            # it will still be retried where it left off.) This is usually a best
            # practice, but if you're using Python older than 2.6 or if you're
            # running on App Engine, you should set the chunksize to something like
            # 1024 * 1024 (1 megabyte).
            media_body=MediaFileUpload(options.file, chunksize=-1, resumable=True)
        )
        print("initalized")
        return insert_request

    def upload_thumbnail(self, youtube, video_id, file):
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(file, chunksize=-1, resumable=True)
        ).execute()

    def build_resource(self, properties):
        resource = {}
        for p in properties:
            # Given a key like "snippet.title", split into "snippet" and "title", where
            # "snippet" will be an object and "title" will be a property in that object.
            prop_array = p.split('.')
            ref = resource
            for pa in range(0, len(prop_array)):
                is_array = False
                key = prop_array[pa]

                # For properties that have array values, convert a name like
                # "snippet.tags[]" to snippet.tags, and set a flag to handle
                # the value as an array.
                if key[-2:] == '[]':
                    key = key[0:len(key) - 2:]
                    is_array = True

                if pa == (len(prop_array) - 1):
                    # Leave properties without values out of inserted resource.
                    if properties[p]:
                        if is_array:
                            ref[key] = properties[p].split(',')
                        else:
                            ref[key] = properties[p]
                elif key not in ref:
                    # For example, the property is "snippet.title", but the resource does
                    # not yet have a "snippet" object. Create the snippet object here.
                    # Setting "ref = ref[key]" means that in the next time through the
                    # "for pa in range ..." loop, we will be setting a property in the
                    # resource's "snippet" object.
                    ref[key] = {}
                    ref = ref[key]
                else:
                    # For example, the property is "snippet.description", and the resource
                    # already has a "snippet" object.
                    ref = ref[key]
        return resource

    def remove_empty_kwargs(self, **kwargs):
        good_kwargs = {}
        if kwargs is not None:
            for key, value in kwargs.items():
                if value:
                    good_kwargs[key] = value
        return good_kwargs

    def playlists_list_by_channel_id(self, client, **kwargs):
        # See full sample for function
        kwargs = self.remove_empty_kwargs(**kwargs)

        response = client.playlists().list(
            **kwargs
        ).execute()

        print(response)
        return response

    def playlist_items_insert(self, youtube, properties, **kwargs):
        # See full sample for function
        resource = self.build_resource(properties)

        # See full sample for function
        kwargs = self.remove_empty_kwargs(**kwargs)

        response = youtube.playlistItems().insert(
            body=resource,
            **kwargs
        ).execute()

        print(response)

        return response

    def get_content_owner_id(youtube_partner, youtube):
        try:
            content_owners_list_response = youtube.contentOwners().list(
                fetchMine=True
            ).execute()
        except HttpError as e:
            if INVALID_CREDENTIALS in e.content:
                logging.error("The request is not authorized by a Google Account that "
                              "is linked to a YouTube content owner. Please delete '%s' and "
                              "re-authenticate with a YouTube content owner account." %
                              CACHED_CREDENTIALS_FILE)
                exit(1)
            else:
                raise

        # This returns the CMS user id of the first entry returned
        # by youtubePartner.contentOwners.list()
        # See https://developers.google.com/youtube/partner/docs/v1/contentOwners/list
        # Normally this is what you want, but if you authorize with a Google Account
        # that has access to multiple YouTube content owner accounts, you need to
        # iterate through the results.
        return content_owners_list_response["items"][0]["id"]

    def resumable_upload(self, insert_request):
        response = None
        error = None
        retry = 0
        print('resumable upload')
        video_id = ""
        while response is None:
            try:
                print("Uploading file...")
                status, response = insert_request.next_chunk()
                if 'id' in response:
                    print("Video id '%s' was successfully uploaded." % response['id'])
                    video_id = response['id']
                else:
                    exit("The upload failed with an unexpected response: %s" % response)
            except HttpError as e:
                if e.resp.status in RETRIABLE_STATUS_CODES:
                    error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status,
                                                                         e.content)
                else:
                    raise
            except RETRIABLE_EXCEPTIONS as e:
                error = "A retriable error occurred: %s" % e

            if error is not None:
                print(error)
                retry += 1
                if retry > MAX_RETRIES:
                    exit("No longer attempting to retry.")

                max_sleep = 2 ** retry
                sleep_seconds = random.random() * max_sleep
                print("Sleeping %f seconds and then retrying..." % sleep_seconds)
                time.sleep(sleep_seconds)

        return video_id

    def download_video(self,video_name, link):

        VIDEO_FILENAME = video_name+'_test_video.mp4'
        # urlretrieve(link, VIDEO_FILENAME)

        r = requests.get(link)
        if r.status_code == 200:
            with open(VIDEO_FILENAME, 'wb') as f:
                for chunk in r.iter_content(chunk_size=2048):
                    if chunk:
                        f.write(chunk)

        return VIDEO_FILENAME

    def delete_video(self, video_name):
        os.remove(video_name)
        print("deleted")
        return

