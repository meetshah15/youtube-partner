#!/usr/bin/python
import json
import logging
import random
import time
from optparse import OptionParser

import httplib2
import os

from apiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from oauth2client.file import Storage
from oauth2client.client import flow_from_clientsecrets
from oauth2client.tools import argparser, run_flow
from oauth2client import client


# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google Developers Console at
# https://console.developers.google.com/.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
# CLIENT_SECRETS_FILE = "client_secrets.json"
CLIENT_SECRETS_FILE = "client_secret_new.json"
ASSETLABEL_EXISTS = "assetLabelExists"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the Developers Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))
pwd = os.path.dirname(os.path.abspath(__file__))

YOUTUBE_SCOPES = (
  # This OAuth 2.0 access scope allows for read-only access to the authenticated
  # user's account, but not other types of account access.
  "https://www.googleapis.com/auth/youtube.readonly",
  # This OAuth 2.0 scope grants access to YouTube Content ID API functionality.
  "https://www.googleapis.com/auth/youtubepartner")
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_PARTNER_API_SERVICE_NAME = "youtubePartner"
YOUTUBE_PARTNER_API_VERSION = "v1"


def parse_options(temp_video, video_title, video_description, keywords, channel_id):
  parser = OptionParser()
  parser.add_option("--file", dest="file", help="Video file to upload")
  parser.add_option("--title", dest="title", help="Video title",
                    default="Test Title")
  parser.add_option("--description", dest="description",
                    help="Video description",
                    default="Test Description")
  parser.add_option("--category", dest="category",
                    help="Numeric video category. " +
                         "See https://developers.google.com/youtube/v3/docs/videoCategories/list",
                    default="22")
  parser.add_option("--keywords", dest="keywords",
                    help="Video keywords, comma separated", default="")
  parser.add_option("--privacyStatus", dest="privacyStatus",
                    help="Video privacy status: public, private or unlisted",
                    default="public")
  parser.add_option("--policyId", dest="policyId",
                    help="Optional id of a saved claim policy")
  parser.add_option("--channelId", dest="channelId",
                    help="Id of the channel to upload to. Must be managed by your CMS account")

  (options, args) = parser.parse_args(
    ['--file', temp_video, '--title', video_title, '--description', video_description, '--keywords', keywords,
     '--channelId', channel_id])

  return options

# Authorize the request and store authorization credentials.


def get_credentials():
  with open("devops/auto_upload_to_youtube.py-oauth2.json", 'r') as f:
    json_ = json.load(f)
    credentials = client.Credentials.new_from_json(json_)
  return credentials


def get_authenticated_services(args):
  flow = flow_from_clientsecrets(pwd + '/' +CLIENT_SECRETS_FILE,
    scope=" ".join(YOUTUBE_SCOPES),
    message=MISSING_CLIENT_SECRETS_MESSAGE)

  storage = Storage("%s-oauth2.json" % "devops/auto_upload_to_youtube.py")
  credentials = storage.get()

  # credentials = get_credentials()

  if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, args)

  youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
    http=credentials.authorize(httplib2.Http()))

  youtube_partner = build(YOUTUBE_PARTNER_API_SERVICE_NAME,
    YOUTUBE_PARTNER_API_VERSION, http=credentials.authorize(httplib2.Http()))

  return (youtube, youtube_partner)


def get_content_owner_id(youtube_partner):
  # Call the contentOwners.list method to retrieve the ID of the content
  # owner associated with the currently authenticated user's account. If the
  # authenticated user's has access to multiple YouTube content owner accounts,
  # you need to iterate through the results to find the appropriate one.
  content_owners_list_response = youtube_partner.contentOwners().list(
    fetchMine=True
  ).execute()

  return content_owners_list_response["items"][0]["id"]


def list_managed_channels(youtube, content_owner_id):
  print("Channels managed by content owner '%s':" % content_owner_id)

  # Retrieve a list of the channels that the content owner manages.
  channels_list_request = youtube.channels().list(
    onBehalfOfContentOwner=content_owner_id,
    managedByMe=True,
    part="snippet",
    maxResults=50
  )

  while channels_list_request:
    channels_list_response = channels_list_request.execute()

    for channel_item in channels_list_response["items"]:
      channel_title = channel_item["snippet"]["title"]
      channel_id = channel_item["id"]
      print ("%s (%s)" % (channel_title, channel_id))

    channels_list_request = youtube.channels().list_next(
      channels_list_request, channels_list_response)


def create_asset_label(youtube_partner, content_owner_id, labelName):
  # Create a new asset label.
  body = dict(
    labelName=labelName
  )

  try:
    asset_labels_insert_response = youtube_partner.assetLabels().insert(
      onBehalfOfContentOwner=content_owner_id,
      body=body
    ).execute()
    logging.info("Created new asset label '%s'." % asset_labels_insert_response["labelName"])
    return asset_labels_insert_response["labelName"]
  except Exception as e:
    if ASSETLABEL_EXISTS in e.content:
      logging.error("Asset label '%s' already exists." % labelName)
      return labelName
    else:
      raise e


def upload(youtube, content_owner_id, options):
    if options.keywords:
      tags = options.keywords.split(",")
    else:
      tags = None

    insert_request = youtube.videos().insert(
      onBehalfOfContentOwner=content_owner_id,
      onBehalfOfContentOwnerChannel=options.channelId,
      part="snippet,status",
      body=dict(
        snippet=dict(
          title=options.title,
          description=options.description,
          tags=tags,
          categoryId=options.category
        ),
        status=dict(
          privacyStatus=options.privacyStatus
        )
      ),
      # chunksize=-1 means that the entire file will be uploaded in a single
      # HTTP request. (If the upload fails, it will still be retried where it
      # left off.) This is usually a best practice, but if you're using Python
      # older than 2.6 or if you're running on App Engine, you should set the
      # chunksize to something like 1024 * 1024 (1 megabyte).
      media_body=MediaFileUpload(options.file, chunksize=-1, resumable=True)
    )

    response = None
    error = None
    retry = 0
    duration_seconds = 0
    while response is None:
      try:
        logging.debug("Uploading file...")

        start_seconds = time.time()
        status, response = insert_request.next_chunk()
        delta_seconds = time.time() - start_seconds
        duration_seconds += delta_seconds

        if "id" in response:
          return (response["id"], duration_seconds)
        else:
          logging.error("The upload failed with an unexpected response: %s" %
                        response)
          exit(1)
      except HttpError as e:
        if e.resp.status in RETRIABLE_STATUS_CODES:
          error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status,
                                                               e.content)
        else:
          raise
      except RETRIABLE_EXCEPTIONS as e:
        error = "A retriable error occurred: %s" % e

      if error is not None:
        logging.error(error)
        retry += 1
        if retry > MAX_RETRIES:
          logging.error("No longer attempting to retry.")
          exit(1)

        max_sleep = 2 ** retry
        sleep_seconds = random.random() * max_sleep
        logging.debug("Sleeping %f seconds and then retrying..." % sleep_seconds)
        time.sleep(sleep_seconds)


def create_asset(youtube_partner, content_owner_id, options):
  # Create a new web asset, which corresponds to a video that was originally
  # distributed online. The asset will be linked to the corresponding YouTube
  # video via a claim that is created later in the script.
  body = dict(
    type="web",
    metadata=dict(
      title=options.title,
      description=options.description
    )
  )

  assets_insert_response = youtube_partner.assets().insert(
    onBehalfOfContentOwner=content_owner_id,
    body=body
  ).execute()

  return assets_insert_response["id"]


def set_asset_ownership(youtube_partner, content_owner_id, asset_id):
  # Update the asset's ownership data. This example indicates that the content
  # owner owns 100% of the asset worldwide.
  body = dict(
    general=[dict(
      owner=content_owner_id,
      ratio=100,
      type="exclude",
      territories=[]
    )]
  )

  youtube_partner.ownership().update(
    onBehalfOfContentOwner=content_owner_id,
    assetId=asset_id,
    body=body
  ).execute()


def claim_video(youtube_partner, content_owner_id, asset_id, video_id,
  policy_id):
  # Create a claim resource. Identify the video being claimed, the asset
  # that represents the claimed content, the type of content being claimed,
  # and the policy that you want to apply to the claimed video.
  #
  # You can identify a policy by using the policy_id of an existing policy as
  # obtained via youtubePartner.policies.list(). If you update that policy at
  # a later time, the updated policy will also be applied to a claim. If you
  # do not provide a policy_id, the code creates a new inline policy that
  # indicates that the video should be monetized.
  if policy_id:
    policy = dict(
      id=policy_id
    )
  else:
    policy = dict(
      rules=[dict(
        action="monetize"
      )]
    )

  body = dict(
    assetId=asset_id,
    videoId=video_id,
    policy=policy,
    contentType="audiovisual"
  )

  claims_insert_response = youtube_partner.claims().insert(
    onBehalfOfContentOwner=content_owner_id,
    body=body
  ).execute()

  return claims_insert_response["id"]


def set_advertising_options(youtube_partner, content_owner_id, video_id):
  # Enable ads for the video. This example enables the TrueView ad format.
  body = dict(
    adFormats=["trueview_instream"]
  )

  youtube_partner.videoAdvertisingOptions().update(
    videoId=video_id,
    onBehalfOfContentOwner=content_owner_id,
    body=body
  ).execute()


def upload_thumbnail(youtube, content_owner_id, video_id, image_file_path):

  request = youtube.thumbnails().set(
    videoId=video_id,
    onBehalfOfContentOwner=content_owner_id,
    # TODO: For this request to work, you must replace "YOUR_FILE"
    #       with a pointer to the actual file you are uploading.
    media_body=MediaFileUpload(image_file_path)
  )
  response = request.execute()
  return response


if __name__ == "__main__":
  args = argparser.parse_args()
  (youtube, youtube_partner) = get_authenticated_services()
  content_owner_id = get_content_owner_id(youtube_partner)
  list_managed_channels(youtube, content_owner_id)
