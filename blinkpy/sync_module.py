"""Defines a sync module for Blink."""

import logging
from shutil import copyfileobj

from requests.structures import CaseInsensitiveDict
from blinkpy import api
from blinkpy.camera import BlinkCamera
from blinkpy.helpers.constants import ONLINE

_LOGGER = logging.getLogger(__name__)


class BlinkSyncModule():
    """Class to initialize sync module."""

    def __init__(self, blink, network_name, network_id):
        """
        Initialize Blink sync module.

        :param blink: Blink class instantiation
        """
        self.blink = blink
        self._auth_header = blink.auth_header
        self.network_id = network_id
        self.region = blink.region
        self.region_id = blink.region_id
        self.name = network_name
        self.serial = None
        self.status = None
        self.sync_id = None
        self.host = None
        self.summary = None
        self.homescreen = None
        self.network_info = None
        self.events = []
        self.cameras = CaseInsensitiveDict({})
        self.motion = {}
        self.last_record = {}

    @property
    def attributes(self):
        """Return sync attributes."""
        attr = {
            'name': self.name,
            'id': self.sync_id,
            'network_id': self.network_id,
            'serial': self.serial,
            'status': self.status,
            'region': self.region,
            'region_id': self.region_id,
        }
        return attr

    @property
    def urls(self):
        """Return device urls."""
        return self.blink.urls

    @property
    def online(self):
        """Return boolean system online status."""
        return ONLINE[self.status]

    @property
    def arm(self):
        """Return status of sync module: armed/disarmed."""
        return self.network_info['network']['armed']

    @arm.setter
    def arm(self, value):
        """Arm or disarm system."""
        if value:
            return api.request_system_arm(self.blink, self.network_id)

        return api.request_system_disarm(self.blink, self.network_id)

    def start(self):
        """Initialize the system."""
        response = api.request_syncmodule(self.blink, self.network_id)
        try:
            self.summary = response['syncmodule']
            self.network_id = self.summary['network_id']
        except (TypeError, KeyError):
            _LOGGER.error(("Could not retrieve sync module information "
                           "with response: %s"), response)
            return False

        try:
            self.sync_id = self.summary['id']
            self.serial = self.summary['serial']
            self.status = self.summary['status']
        except KeyError:
            _LOGGER.error("Could not extract some sync module info: %s",
                          response)

        self.events = self.get_events()
        self.homescreen = api.request_homescreen(self.blink)
        self.network_info = api.request_network_status(self.blink,
                                                       self.network_id)

        self.check_new_videos()
        camera_info = self.get_camera_info()
        for camera_config in camera_info:
            name = camera_config['name']
            self.cameras[name] = BlinkCamera(self)
            self.motion[name] = False
            self.cameras[name].update(camera_config, force_cache=True)

        return True

    def get_events(self):
        """Retrieve events from server."""
        response = api.request_sync_events(self.blink, self.network_id)
        try:
            return response['event']
        except (TypeError, KeyError):
            _LOGGER.error("Could not extract events: %s", response)
            return False

    def get_camera_info(self):
        """Retrieve camera information."""
        response = api.request_cameras(self.blink, self.network_id)
        try:
            return response['devicestatus']
        except (TypeError, KeyError):
            _LOGGER.error("Could not extract camera info: %s", response)
            return []

    def refresh(self, force_cache=False):
        """Get all blink cameras and pulls their most recent status."""
        self.events = self.get_events()
        self.homescreen = api.request_homescreen(self.blink)
        self.network_info = api.request_network_status(self.blink,
                                                       self.network_id)
        camera_info = self.get_camera_info()
        self.check_new_videos()
        for camera_config in camera_info:
            name = camera_config['name']
            self.cameras[name].update(camera_config, force_cache=force_cache)


    def save_video(self, addr, path):
        url = "{}{}".format(self.urls.base_url, addr)
        video = api.http_get(self.blink,
                             url=url,
                             stream=True,
                             json=False)
        if video is None:
            _LOGGER.error("Cannot download video %s.", addr)
            return
        with open(path, 'wb') as vidfile:
            copyfileobj(video.raw, vidfile)

    def get_video_url(self, addr):
        return "{}{}".format(self.urls.base_url, addr)

    def get_videos(self, start_page=0, end_page=1):
        """
        Retrieve last recorded videos per camera.

        :param start_page: Page to start reading from on blink servers
                           (defaults to 0)
        :param end_page: Page to stop reading from (defaults to 1)
        """
        videos = list()
        all_dates = dict()

        for page_num in range(start_page, end_page + 1):
            this_page = api.request_videos(self.blink, page=page_num)
            if not this_page:
                break
            elif 'message' in this_page:
                _LOGGER.warning("Could not retrieve videos. Message: %s",
                                this_page['message'])
                break

            videos.append(this_page)
        _LOGGER.debug("Getting videos from page %s through %s",
                      start_page,
                      end_page)
        for page in videos:
            for entry in page:
                try:
                    camera_name = entry['camera_name']
                    clip_addr = entry['address']
                    thumb_addr = entry['thumbnail']
                except TypeError:
                    _LOGGER.warning("Could not extract video information.")
                    break

                clip_date = entry['created_at']

                try:
                    self.all_clips[camera_name][clip_date] = clip_addr
                except KeyError:
                    self.all_clips[camera_name] = {clip_date: clip_addr}

                if camera_name not in all_dates:
                    all_dates[camera_name] = list()
                if clip_date not in all_dates[camera_name]:
                    all_dates[camera_name].append(clip_date)
                    try:
                        self.videos[camera_name].append(
                            {
                                'clip': clip_addr,
                                'thumb': thumb_addr,
                            }
                        )
                    except KeyError:
                        self.videos[camera_name] = [
                            {
                                'clip': clip_addr,
                                'thumb': thumb_addr,
                            }
                        ]
        self.record_dates = all_dates
        _LOGGER.debug("Retrieved a total of %s records", len(all_dates))
        return self.videos


    def check_new_videos(self):
        """Check if new videos since last refresh."""
        resp = api.request_videos(self.blink,
                                  time=self.blink.last_refresh,
                                  page=0)

        for camera in self.cameras.keys():
            self.motion[camera] = False

        try:
            info = resp['videos']
        except (KeyError, TypeError):
            _LOGGER.warning("Could not check for motion. Response: %s", resp)
            return False

        for entry in info:
            try:
                name = entry['camera_name']
                clip = entry['address']
                timestamp = entry['created_at']
                self.motion[name] = True
                self.last_record[name] = {'clip': clip, 'time': timestamp}
            except KeyError:
                _LOGGER.debug("No new videos since last refresh.")

        return True
