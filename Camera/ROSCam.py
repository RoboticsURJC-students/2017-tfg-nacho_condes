#
# Created on Dec, 2019
#
# @author: naxvm
#
# Class to abstract a RGBD Camera into OpenCV images,
# Provides the methods to keep it constantly refreshed.

import threading
import numpy as np
import rospy
from sensor_msgs.msg import Image
import cv_bridge
import cv2
import time
import rosbag

IMAGE_HEIGHT = 480
IMAGE_WIDTH = 640

class ROSCam:

    def __init__ (self, topics, rosbag_path=None):
        ''' Camera class gets new images from the ROS topics or a recorded rosbag
        and convert them into OpenCV format, offering the latest one to the caller.

        A control thread is not necessary (the subscribers are controlled
        by rospy threads).
        '''
        self.use_bag = rosbag_path is not None
        if self.use_bag:
            # Create iterators for the rosbag
            self.bag = rosbag.Bag(rosbag_path)
            self.rgb_iter = self.bag.read_messages(topics['RGB'])
            self.depth_iter = self.bag.read_messages(topics['Depth'])
        else:
            # Wait for the topics to be advertised
            topic_names, _ = map(list, zip(*rospy.get_published_topics()))
            while topics['RGB'] not in topic_names or topics['Depth'] not in topic_names:
                print('Waiting for the topics to be advertised...')
                time.sleep(1)
                topic_names, _ = map(list, zip(*rospy.get_published_topics()))

            # Subscribers
            self.rgb_lst = rospy.Subscriber(topics['RGB'], Image, self.__rgbCallback, queue_size=1)
            self.d_lst = rospy.Subscriber(topics['Depth'], Image, self.__depthCallback, queue_size=1)

        # Two bridges for concurrency issues
        self.rgb_bridge = cv_bridge.CvBridge()
        self.depth_bridge = cv_bridge.CvBridge()

        # Placeholders
        self.__rgb_data = None
        self.__depth_data = None

        self.lock = threading.Lock()

    def getBagLength(self, topics):
        ''' Retrieve the length of the bag. '''
        bag_topics = self.bag.get_type_and_topic_info()
        rgb_info = bag_topics[1][topics['RGB']]
        message_count = rgb_info[1]

        return int(message_count / 2)


    def __rgbCallback(self, rgb_data):
        self.lock.acquire()
        self.__rgb_data = rgb_data
        rospy.logdebug("RGB updated")
        self.lock.release()

    def __depthCallback(self, depth_data):
        self.lock.acquire()
        self.__depth_data = depth_data
        rospy.logdebug("Depth updated")
        self.lock.release()

    def getImages(self):
        ''' Return the latest images from a rosbag or from the topic. '''
        if self.use_bag:
            kk = next(self.rgb_iter)
            # print(type(kk), len(kk))
            _, rgb_data, _ = next(self.rgb_iter)
            _, depth_data, _ = next(self.depth_iter)
        else:
            rgb_data = self.__rgb_data
            depth_data = self.__depth_data

        rgb_image = self.rgb_bridge.imgmsg_to_cv2(rgb_data, rgb_data.encoding)
        depth_image = self.depth_bridge.imgmsg_to_cv2(depth_data, depth_data.encoding)

        return rgb_image, depth_image
