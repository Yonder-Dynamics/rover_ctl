#!/usr/bin/env python
import math, rospy
from rover_ctl.msg import MotorCMD
from nav_msgs.msg import Odometry
from ControlState import ControlState
from SearchState import SearchState

# Using ROS pose for things

# Given a goal vector:
# Turn to desired direction
# Move to desired position
# Turn to final direction

MAX_MOTOR_SPEED = 255
#MAX_MOTOR_SPEED = 200
HEADING_DEAD_BAND = math.pi/8
POSITION_DEAD_BAND = 1.0 # m

class FollowingSearchState (ControlState):
    def __init__(self, confidence_thres,
            maxSpeedAtDist, maxSpeedAtAngle, minDriveSpeed, minTurningSpeed):
        ControlState.__init__(self, maxSpeedAtDist,
                maxSpeedAtAngle, minDriveSpeed, minTurningSpeed)
        SearchState.__init__(self, confidence_thres)
        self.state = "idle" # "aiming" "moving" "finetuning"
        self.goalPose = None
        self.path = None
        self.currentPose = None
        self.goalReached = True
        self.receivedPath = False
        self.parent = None

    def attach(self):
        ControlState.attach(self)
        SearchState.attach(self)
        self.goalPose = None
        self.path = None
        self.currentPose = None
        self.goalReached = True
        self.receivedPath = False
        self.odom_sub = rospy.Subscriber("/fusion/local_fusion/filtered", Odometry, self.update)
        self.pub = rospy.Publisher("/motor_ctl", MotorCMD, queue_size=10)
        self.setPath(self.parent.path)

    def detach(self):
        ControlState.detach(self)
        SearchState.detach(self)
        self.odom_sub.unregister()

    def foundCallback(self, orientation, angle, dist):
        self.parent.handleSignal("found")

    def setPath(self, pathMsg):
        i = 0;
        j = 0;
        dist = 0;
        smallestDist = 99999;
        for k in self.path.poses:
            i += 1
            dist = math.sqrt(
                    (self.currentPose.position.x - k.pose.position.x)**2 +
                    (self.currentPose.position.y - k.pose.position.y)**2 +
                    (self.currentPose.position.z - k.pose.position.z)**2
                    )
            if dist < smallestDist:
                smallestDist = dist
                j = i
        self.setGoalCallback(self.path.poses[j+1].pose)

    def calcGoalAngle(self, roverPose):
        return math.atan2(self.goalPose.position.y - roverPose.position.y,
                self.goalPose.position.x - roverPose.position.x)

    def setGoalCallback(self, goalMsg):
        self.goalPose = goalMsg
        self.setState("aiming")

    def setState(self, state):
        print("Reached state %s" % state)
        self.state = state

    def update(self, msg):
        roverPose = msg.pose.pose
        self.currentPose = roverPose
        if self.goalPose is not None:
            print("Got path")
            goalHeading = self.calcGoalAngle(roverPose)
            if self.state == "aiming":
                # Turn to desired heading
                reached, motorctl = self.turnTo(goalHeading, roverPose)
                if reached:
                    self.setState("moving")
                else:
                    self.sendCommand(motorctl)
            elif self.state == "finetuning":
                reached, motorctl = self.turnTo(self.getHeading(self.goalPose), roverPose)
                if reached:
                    self.goalPose = None
                    self.setState("idle")
                    self.parent.signal("reached")

                self.sendCommand(motorctl)
            elif self.state == "moving":
                # check if heading is still correct, if not set state to turning
                headingCorrect, motorctl = self.turnTo(goalHeading, roverPose)
                if not headingCorrect:
                    self.sendCommand(motorctl)
                else:
                    # drive
                    reached, motorctl = self.drive(roverPose, self.goalPose)
                    if reached:
                        self.setState("finetuning")
                    else:
                        self.sendCommand(motorctl)

