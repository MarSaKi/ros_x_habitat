#!/usr/bin/env python
import argparse
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
)
import rospy
import message_filters
from geometry_msgs.msg import Twist
from rospy.numpy_msg import numpy_msg
from ros_x_habitat.msg import PointGoalWithGPSCompass, DepthImage
from sensor_msgs.msg import Image
from std_msgs.msg import Int16
from message_filters import TimeSynchronizer
from cv_bridge import CvBridge, CvBridgeError
from habitat.sims.habitat_simulator.actions import _DefaultHabitatSimActions
from math import radians
import numpy as np


# load sensor readings and actions from disk
num_readings = 27
readings_rgb_discrete = []
readings_depth_discrete = []
readings_ptgoal_with_comp_discrete = []
actions_discrete = []
for i in range(0, num_readings):
    readings_rgb_discrete.append(np.load(f"/home/lci-user/Desktop/workspace/src/ros_x_habitat/src/tests/obs/rgb-{i}.npy"))
    readings_depth_discrete.append(np.load(f"/home/lci-user/Desktop/workspace/src/ros_x_habitat/src/tests/obs/depth-{i}.npy"))
    readings_ptgoal_with_comp_discrete.append(np.load(f"/home/lci-user/Desktop/workspace/src/ros_x_habitat/src/tests/obs/pointgoal_with_gps_compass-{i}.npy"))
    actions_discrete.append(np.load(f"/home/lci-user/Desktop/workspace/src/ros_x_habitat/src/tests/acts/action-{i}.npy"))



class MockHabitatAgentNode:
    r"""
        A mock agent that checks if sensor readings from the environment
        node is correct, and publishes pre-recorded actions back to the
        environment.    
    """
    def __init__(self, enable_physics: bool = False):
        self.enable_physics = enable_physics
        self.sensor_pub_rate = 10
        self.observations_count = 0

        self.sub_queue_size = 10
        self.pub_queue_size = 10

        if self.enable_physics:
            self.control_period = 1.0

        # count the number of frames received from Habitat simulator;
        # reset to 0 every time an action is completed
        # not applicable in discrete mode
        if self.enable_physics:
            self.count_frames = 0

        # publish to command topics
        if self.enable_physics:
            self.pub = rospy.Publisher("cmd_vel", Twist, queue_size=self.pub_queue_size)
        else:
            self.pub = rospy.Publisher("action", Int16, queue_size=self.pub_queue_size)

        # subscribe to sensor topics
        self.sub_rgb = message_filters.Subscriber("rgb", Image)
        self.sub_depth = message_filters.Subscriber("depth", numpy_msg(DepthImage))
        self.sub_pointgoal_with_gps_compass = message_filters.Subscriber("pointgoal_with_gps_compass", PointGoalWithGPSCompass)
        
        # filter sensor topics with time synchronizer
        self.ts = TimeSynchronizer([self.sub_rgb, self.sub_depth, self.sub_pointgoal_with_gps_compass], queue_size=self.sub_queue_size)
        self.ts.registerCallback(self.callback_rgbd)
        
        print("agent making sure env subscribed to command topic...")
        while self.pub.get_num_connections() == 0:
            pass

        print("agent initialized")
    
    def depthmsg_to_cv2(self, depth_msg):
        r"""
        Converts a ROS DepthImage message to a Habitat depth observation.
        :param depth_msg: ROS depth message
        :returns: depth observation as a numpy array
        """
        w = depth_msg.width
        h = depth_msg.height
        depth_img = np.reshape(depth_msg.data.astype(np.float32), (h, w))
        return depth_img

    def msgs_to_obs(self, rgb_msg: Image = None, depth_msg: DepthImage = None, pointgoal_with_gps_compass_msg: PointGoalWithGPSCompass = None) -> Dict[str, Any]:
        r"""
        Converts ROS messages into Habitat observations.
        :param rgb_msg: RGB sensor observations packed in a ROS message
        :param depth_msg: Depth sensor observations packed in a ROS message
        :param pointgoal_with_gps_compass_msg: Pointgoal + GPS/Compass sensor
            observations packed in a ROS message
        :return: Habitat observations
        """
        observations = {}

        # Convert RGB message
        if rgb_msg is not None:
            observations["rgb"] = CvBridge().imgmsg_to_cv2(rgb_msg, "passthrough").astype(np.float32)
        
        # Convert depth message
        if depth_msg is not None:
            observations["depth"] = self.depthmsg_to_cv2(depth_msg)
            # have to manually add channel info
            observations["depth"] = np.expand_dims(observations["depth"], 2).astype(np.float32)
        
        # Convert pointgoal + GPS/compass sensor message
        if pointgoal_with_gps_compass_msg is not None:
            observations["pointgoal_with_gps_compass"] = np.asarray([pointgoal_with_gps_compass_msg.distance_to_goal, pointgoal_with_gps_compass_msg.angle_to_goal]).astype(np.float32)
        
        return observations
    
    def action_to_msg(self, action: Dict[str, int]):
        r"""
        Converts action produced by Habitat agent to a ROS message.
        :param action: Action produced by Habitat agent.
        :returns: A ROS message of action or velocity command.
        """
        action_id = action["action"]
        msg = ...  # type: Union[Twist, Int16]

        if self.enable_physics:
            msg = Twist()
            msg.linear.x = 0
            msg.linear.y = 0
            msg.linear.z = 0
            msg.angular.x = 0
            msg.angular.y = 0
            msg.angular.z = 0
            # Convert to Twist message in continuous mode
            if action_id == _DefaultHabitatSimActions.STOP:
                pass
            elif action_id == _DefaultHabitatSimActions.MOVE_FORWARD:
                msg.linear.z = 0.25 / self.control_period
            elif action_id == _DefaultHabitatSimActions.TURN_LEFT:
                msg.angular.y = radians(10.0) / self.control_period
            elif action_id == _DefaultHabitatSimActions.TURN_RIGHT:
                msg.angular.y = radians(-10.0) / self.control_period
        else:
            # Convert to Int16 message in discrete mode
            msg = Int16()
            msg.data = action_id
        
        return msg
    
    def callback_rgbd(self, rgb_msg, depth_msg, pointgoal_with_gps_compass_msg):
        r"""
        Checks if simulator readings are correct;
        Produces an action or velocity command periodically from RGBD
        sensor observations, and publish to respective topics.
        :param rgb_msg: RGB sensor readings in ROS message format.
        :param depth_msg: Depth sensor readings in ROS message format.
        :param pointgoal_with_gps_compass_msg: Pointgoal + GPS/Compass readings.
        """
        # convert current_observations from ROS to Habitat format
        observations = self.msgs_to_obs(rgb_msg=rgb_msg, depth_msg=depth_msg, pointgoal_with_gps_compass_msg=pointgoal_with_gps_compass_msg)
        
        if self.observations_count < num_readings:
            # check sensor readings' correctness
            assert np.linalg.norm(observations["rgb"] - readings_rgb_discrete[self.observations_count]) < 1e-5, f"RGB reading at step {self.observations_count} does not match"
            assert np.linalg.norm(observations["depth"] - readings_depth_discrete[self.observations_count]) < 1e-5, f"Depth reading at step {self.observations_count} does not match"
            assert np.linalg.norm(observations["pointgoal_with_gps_compass"] - readings_ptgoal_with_comp_discrete[self.observations_count]) < 1e-5, f"Pointgoal + GPS/Compass reading at step {self.observations_count} does not match"

            # produce an action/velocity once the last action has completed
            # and publish to relevant topics
            if self.enable_physics:
                self.count_frames += 1
                if self.count_frames == (self.sensor_pub_rate * self.control_period) - 1:
                    self.count_frames = 0
                    action = actions_discrete[self.observations_count]
                    vel_msg = self.action_to_msg(action)
                    self.pub.publish(vel_msg)
            else:
                action = {"action": actions_discrete[self.observations_count]}
                action_msg = self.action_to_msg(action)
                self.pub.publish(action_msg)
                print(f"published action after step {self.observations_count}")
            
            self.observations_count += 1

if __name__ == "__main__":
    # parse input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable-physics', default=False, action='store_true')
    args = parser.parse_args()

    rospy.init_node("mock_agent_node")
    mock_agent_node = MockHabitatAgentNode(enable_physics=args.enable_physics)
    rospy.spin()