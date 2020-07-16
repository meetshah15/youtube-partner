import os

from googleapiclient.errors import HttpError
from moviepy.video.io.VideoFileClip import VideoFileClip

import youtube_video_upload
import argparse
from oauth2client import tools

from youtube_api import get_authenticated_services, get_content_owner_id, parse_options, upload, create_asset, \
    set_asset_ownership, claim_video, set_advertising_options, upload_thumbnail


def post_on_youtube_monitised(json_data):

    try:

        pwd = os.path.dirname(os.path.abspath(__file__))

        video_title = json_data['video_title']
        video_description = json_data['video_description']
        video_url = json_data['video_url']
        keywords = json_data['keywords']
        channel_id = json_data['channel_id']
        playlist = json_data['playlist']
        policy_id = json_data['policy_id']

        youtubeUpload = youtube_video_upload.YoutubeUpload()
        temp_video = youtubeUpload.download_video("news18",
                                                  video_url)

        parser = argparse.ArgumentParser(parents=[tools.argparser])
        (youtube, youtube_partner) = get_authenticated_services(parser)

        content_owner_id = get_content_owner_id(youtube_partner)

        options = parse_options(temp_video, video_title, video_description, keywords, channel_id)

        (video_id, duration_seconds) = upload(youtube, content_owner_id, options)
        print("Video uploaded successfully")

        asset_id = create_asset(youtube_partner, content_owner_id,
                                options)
        print("We've the asset ids")

        set_asset_ownership(youtube_partner, content_owner_id, asset_id)
        print("Ownership set successfully")

        claim_id = claim_video(youtube_partner, content_owner_id, asset_id,
                               video_id, policy_id)
        print("We've the claim id")

        set_advertising_options(youtube_partner, content_owner_id, video_id)
        print("We've successfully completed monetizaing the video")

        try:
            purge_list = list()

            print("Starting thumbnail generation")

            video_clip = VideoFileClip(temp_video)
            purge_list.append(video_clip)
            image_path = pwd + '/' + video_id + '.jpg'
            video_clip.save_frame(image_path, 4)

            response = upload_thumbnail(youtube, content_owner_id, video_id, image_path)
            print("Thumbnail applied successfully")

            youtubeUpload.delete_video(temp_video)
            kill_ffmpeg_process(purge_list)
            return video_id

        except HttpError as e:
            print("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))
            if video_id:
                return video_id

        return False
    except Exception as e:
        raise e


def kill_ffmpeg_process(list_of_clips):
    for index_, ele in enumerate(list_of_clips):
        try:
            try:
                ele.close()
            except:
                pass
            try:
                ele.reader = None
            except:
                pass
        except Exception as e:
            pass
    return
