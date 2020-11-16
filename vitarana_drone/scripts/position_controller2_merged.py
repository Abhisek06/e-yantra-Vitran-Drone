#!/usr/bin/env python

'''**********************************
E-yantra
Theme: Vitran Drone
Task: task1B
Purpose: Position controller
Team ID : 0583
Team name : !ABHIMANYU 
**********************************'''

# Importing the required libraries
from vitarana_drone.msg import *
from pid_tune.msg import PidTune
from sensor_msgs.msg import NavSatFix
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32,String
import rospy
import numpy as np
import time
import tf

from pyzbar.pyzbar import decode
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError
import cv2
from vitarana_drone.srv import Gripper,GripperResponse
from sensor_msgs.msg import LaserScan

class Edrone():
    """docstring for Edrone"""
    def __init__(self):
        rospy.init_node('position_controller2')  # initializing ros node with name position_controller

        # This will contain the current location of Edrone. [latitude, longitude, altitude ]
        # this value is updating each time in gps callback function
        self.drone_location = [0.0, 0.0, 0.0]

        #To store the intermediate setpoints. [latitude , longitude, altitude ]
        self.setpoint_location = [19.0, 72.0, 3.0]

        #To store the final setpoint. [latitude , longitude, altitude ]
        self.setpoint_final = [19.0, 72.0, 3.0]  

        # This is the location of destination of box retrive from qr code. [latitude , longitude, altitude ]
        self.box_position = [0.0, 0.0, 0.0]  

        # This will contain the current orientation of eDrone in quaternion format. [x,y,z,w]
        # This value is updating each time in imu callback function
        self.drone_orientation_quaternion = [0.0, 0.0, 0.0, 0.0]

        # This will contain the current orientation of eDrone converted in euler angles form. [r,p,y]
        self.drone_orientation_euler = [0.0, 0.0, 0.0]

        self.laser_negative_latitude = 0
        self.laser_positive_longitude = 0
        self.laser_negative_longitude = 0
        self.laser_positive_latitude = 0

        # Declaring rpyt_cmd of message type edrone_cmd and initializing values 
        # { rpyt_cmd --> roll, pitch, yaw, throttle command}
        self.rpyt_cmd = edrone_cmd()
        self.rpyt_cmd.rcRoll = 1500.0
        self.rpyt_cmd.rcPitch = 1500.0
        self.rpyt_cmd.rcYaw = 1500.0
        self.rpyt_cmd.rcThrottle = 1500.0

        # Declaring error values and tolerences to publish for visualization in plotjuggler
        self.latitude_Error = Float32()
        self.latitude_Error.data = 0.0
        self.latitude_Up = Float32()
        self.latitude_Up.data = 0.000004517
        self.latitude_Low = Float32()
        self.latitude_Low.data = -0.000004517

        self.longitude_Error = Float32()
        self.longitude_Error.data = 0.0
        self.longitude_Up = Float32()
        self.longitude_Up.data = 0.0000047487
        self.longitude_Low = Float32()
        self.longitude_Low.data = -0.0000047487

        self.altitude_Error = Float32()
        self.altitude_Error.data = 0.0
        self.altitude_Up = Float32()
        self.altitude_Up.data = 0.2
        self.altitude_Low = Float32()
        self.altitude_Low.data = -0.2

        # initializing Kp, Kd and ki for [latitude, longitude, altitude] after tunning 
        self.Kp = [1080000, 1140000, 48]
        self.Ki = [0, 0, 0]
        self.Kd = [57600000, 57900000, 3000]
       
        # Declaring variable to store different error values, to be used in PID equations.
        self.change_in_error_value = [0.0, 0.0, 0.0]
        self.error_value = [0.0, 0.0, 0.0]
        self.prev_error_value = [0.0, 0.0, 0.0]
        self.sum_error_value = [0.0, 0.0, 0.0]

        # Declaring maximum and minimum values for roll, pitch, yaw, throttle output.
        self.max_values = [2000.0, 2000.0, 2000.0, 2000.0]
        self.min_values = [1000.0, 1000.0, 1000.0, 1000.0]

        # initializing Publisher for /drone_command, /latitude_error, /longitude_error, /altitude_error and tolerences
        self.rpyt_pub = rospy.Publisher('/drone_command', edrone_cmd, queue_size=1)
        self.latitude_error = rospy.Publisher('/latitude_error', Float32, queue_size=1)
        self.longitude_error = rospy.Publisher('/longitude_error', Float32, queue_size=1)
        self.altitude_error = rospy.Publisher('/altitude_error', Float32, queue_size=1)

        self.latitude_up = rospy.Publisher('/latitude_up', Float32, queue_size=1)
        self.longitude_up = rospy.Publisher('/longitude_up', Float32, queue_size=1)
        self.altitude_up = rospy.Publisher('/altitude_up', Float32, queue_size=1)
        self.latitude_low = rospy.Publisher('/latitude_low', Float32, queue_size=1)
        self.longitude_low = rospy.Publisher('/longitude_low', Float32, queue_size=1)
        self.altitude_low = rospy.Publisher('/altitude_low', Float32, queue_size=1)

        # Subscribing to /edrone/gps, /pid_tuning_roll, /pid_tuning_pitch, /pid_tuning_yaw {used these GUIs only to tune ;-) }
        rospy.Subscriber('/edrone/gps', NavSatFix, self.gps_callback)
        rospy.Subscriber('/edrone/imu/data', Imu, self.imu_callback)
        # rospy.Subscriber('/pid_tuning_roll', PidTune, self.roll_set_pid)        # for latitude
        # rospy.Subscriber('/pid_tuning_pitch', PidTune, self.pitch_set_pid)      # for longitude
        # rospy.Subscriber('/pid_tuning_yaw', PidTune, self.yaw_set_pid)          # for altitude
        rospy.Subscriber('/qrValue', String, self.qr_callback)
        rospy.Subscriber('/edrone/range_finder_top',LaserScan,self.range_finder_callback)


    #Callback function for LaserScan
    def range_finder_callback(self, msg):
        if(self.drone_orientation_euler[2]<np.pi/4 and self.drone_orientation_euler[2]>-np.pi/4):
            self.laser_negative_longitude,self.laser_positive_latitude,self.laser_positive_longitude,self.laser_negative_latitude = msg.ranges[:-1]

        elif(self.drone_orientation_euler[2]<3*np.pi/4 and self.drone_orientation_euler[2]>np.pi/4):
            self.laser_negative_latitude,self.laser_negative_longitude,self.laser_positive_latitude,self.laser_positive_longitude = msg.ranges[:-1]

        elif(self.drone_orientation_euler[2]>3*np.pi/4 or self.drone_orientation_euler[2]<-3*np.pi/4):
            self.laser_positive_longitude,self.laser_negative_latitude,self.laser_negative_longitude,self.laser_positive_latitude = msg.ranges[:-1]

        elif(self.drone_orientation_euler[2]>-3*np.pi/4 and self.drone_orientation_euler[2]<-np.pi/4):
            self.laser_positive_latitude,self.laser_positive_longitude,self.laser_negative_latitude,self.laser_negative_longitude = msg.ranges[:-1]
        # print(self.laser_negative_latitude)

    
    # qr callback function. The function gets executed each time when qr_code publishes /qrValue
    def qr_callback(self,data):
        final_data = data.data
        final_data = final_data.split(",")
        self.box_position[0] = float(final_data[0])
        self.box_position[1] = float(final_data[1])
        self.box_position[2] = float(final_data[2])


    # Imu callback function. The function gets executed each time when imu publishes /edrone/imu/data
    def imu_callback(self, msg):
        self.drone_orientation_quaternion[0] = msg.orientation.x
        self.drone_orientation_quaternion[1] = msg.orientation.y
        self.drone_orientation_quaternion[2] = msg.orientation.z
        self.drone_orientation_quaternion[3] = msg.orientation.w
        # converting the current orientations from quaternion to euler angles 
        (self.drone_orientation_euler[1], self.drone_orientation_euler[0], self.drone_orientation_euler[2]) = tf.transformations.euler_from_quaternion([self.drone_orientation_quaternion[0], self.drone_orientation_quaternion[1], self.drone_orientation_quaternion[2], self.drone_orientation_quaternion[3]])


    # callback function for gps. This function gets executed each time when NavSatFix publishes /edrone/gps
    def gps_callback(self, msg):
        self.drone_location[0] = msg.latitude
        self.drone_location[1] = msg.longitude
        self.drone_location[2] = msg.altitude


    # Callback function for /pid_tuning_roll, we used it to tune latitude
    # This function gets executed each time when /tune_pid publishes /pid_tuning_roll
    def roll_set_pid(self, roll):
        self.Kp[0] = roll.Kp * 600
        self.Ki[0] = roll.Ki * 0.008
        self.Kd[0] = roll.Kd * 30000


    # Callback function for /pid_tuning_pitch, we used it to tune longitude
    # This function gets executed each time when /tune_pid publishes /pid_tuning_pitch
    def pitch_set_pid(self, pitch):
        self.Kp[1] = pitch.Kp * 600 
        self.Ki[1] = pitch.Ki * 0.008
        self.Kd[1] = pitch.Kd * 30000


    # Callback function for /pid_tuning_yaw, we used it to tune altitude
    # This function gets executed each time when /tune_pid publishes /pid_tuning_yaw
    def yaw_set_pid(self, yaw):
        self.Kp[2] = yaw.Kp * 0.06 
        self.Ki[2] = yaw.Ki * 0.008
        self.Kd[2] = yaw.Kd * 30
    

    # this function is containing all the pid equation to control the position of the drone
    def pid(self):
        # updating all the error values to be used in PID equation
        # rospy.Subscriber('/qrValue', String, self.qr_callback)
        for i in range(3):
            self.error_value[i] = self.setpoint_location[i] - self.drone_location[i]
            self.sum_error_value[i] = self.sum_error_value[i] + self.error_value[i]
            self.change_in_error_value[i] = self.error_value[i] - self.prev_error_value[i]
            self.prev_error_value[i] = self.error_value[i]

        # assigning error value to its container to publish
        self.latitude_Error.data = self.error_value[0]
        self.longitude_Error.data = self.error_value[1]
        self.altitude_Error.data = self.error_value[2]

        # PID eqation for latitude
        output0 = self.Kp[0]*self.error_value[0] + self.Ki[0]*self.sum_error_value[0] + self.Kd[0]*self.change_in_error_value[0]
        
        # PID eqation for longitude
        output1 = self.Kp[1]*self.error_value[1] + self.Ki[1]*self.sum_error_value[1] + self.Kd[1]*self.change_in_error_value[1]
        
        # PID equation for altitude
        output2 = self.Kp[2]*self.error_value[2] + self.Ki[2]*self.sum_error_value[2] + self.Kd[2]*self.change_in_error_value[2]
        
        # updating the roll value according to PID output. 
        # {this equation will work fine when there is some yaw. to see detail opne --> https://drive.google.com/file/d/14gjse4HUIi9OoznefjOehh1HU6LUhoO7/view?usp=sharing }
        self.rpyt_cmd.rcRoll = 1500 + output0*np.cos(self.drone_orientation_euler[2]) - output1*np.sin(self.drone_orientation_euler[2])

        # updating the pitch value according to PID output
        self.rpyt_cmd.rcPitch = 1500 + output0*np.sin(self.drone_orientation_euler[2]) + output1*np.cos(self.drone_orientation_euler[2])

        # updating the throttle value according to PID output
        self.rpyt_cmd.rcThrottle = 1500 + output2
        
        # checking the boundary conditions for roll value
        if(self.rpyt_cmd.rcRoll > 1800):
            self.rpyt_cmd.rcRoll = 1800
        elif(self.rpyt_cmd.rcRoll<1200):
            self.rpyt_cmd.rcRoll = 1200

        # checking the boundary conditions for pitch value
        if(self.rpyt_cmd.rcPitch > 1800):
            self.rpyt_cmd.rcPitch = 1800
        elif(self.rpyt_cmd.rcPitch<1200):
            self.rpyt_cmd.rcPitch = 1200

        # checking the boundary conditions for throttle value
        if(self.rpyt_cmd.rcThrottle > 2000):
            self.rpyt_cmd.rcThrottle = 2000
        elif(self.rpyt_cmd.rcThrottle<1000):
            self.rpyt_cmd.rcThrottle = 1000

        # self.rpyt_cmd.rcYaw = 2000.0
        
        # publishing rpyt_cmd to /drone_command
        self.rpyt_pub.publish(self.rpyt_cmd)

        # publishing different error values and tolerences
        self.latitude_error.publish(self.latitude_Error)
        self.longitude_error.publish(self.longitude_Error)
        self.altitude_error.publish(self.altitude_Error)
        self.latitude_up.publish(self.latitude_Up)
        self.longitude_up.publish(self.longitude_Up)
        self.altitude_up.publish(self.altitude_Up)
        self.latitude_low.publish(self.latitude_Low)
        self.longitude_low.publish(self.longitude_Low)
        self.altitude_low.publish(self.altitude_Low)


def gripper_active(state):
    rospy.wait_for_service('/edrone/activate_gripper')
    try:
        gripper_state = rospy.ServiceProxy('/edrone/activate_gripper',Gripper)
        if(state==1):
            resp = gripper_state(activate_gripper = True)
        else:
            resp = gripper_state(activate_gripper = False)
            # return resp
    except rospy.ServiceException as e:
        print("Service call failed: %s"%e)


def is_at_setpoint(setpoint):
        return ((e_drone.drone_location[0] > setpoint[0]+0.000004517 or e_drone.drone_location[0] < setpoint[0]-0.000004517) or 
            (e_drone.drone_location[1] >  setpoint[1]+0.0000047487 or e_drone.drone_location[1] < setpoint[1]-0.0000047487) or 
                (e_drone.drone_location[2] > setpoint[2]+0.2 or e_drone.drone_location[2] < setpoint[2]-0.2))


def avoid_obstacle(prev_ranges):
    altitude = e_drone.drone_location[2]
    delta_altitude = 0
    print("Avoiding Obstacles")
    while(e_drone.laser_negative_latitude <= 6):
    
        if delta_altitude <= 6:
            while(not e_drone.laser_negative_latitude >= 20):
                e_drone.setpoint_location = e_drone.setpoint_location[:-1] + [e_drone.drone_location[2] + 0.5] 
                delta_altitude = e_drone.drone_location[2] - altitude
                e_drone.pid()
                time.sleep(0.05)
        
        '''if(e_drone.laser_positive_longitude >= 4):
            while (e_drone.laser_negative_latitude <= 10):
                e_drone.setpoint_location = [e_drone.drone_location[0], e_drone.drone_location[1]- 0.00005, e_drone.drone_location[2]]
                e_drone.pid()
                time.sleep(0.05)'''
            
def reach_destination():
    
    #if drone is at lower altitude first raise its altitude
    #rospy.loginfo("Destination is:")
    #rospy.loginfo(e_drone.setpoint_final)
    if(e_drone.setpoint_final[2] > e_drone.drone_location[2] or e_drone.drone_location[2] < 24):
        e_drone.setpoint_location = e_drone.drone_location[:-1] + [26]
        while(is_at_setpoint(e_drone.setpoint_location)):
            e_drone.pid()
            time.sleep(0.05)

    #Applying parametric form of line
    e_drone.setpoint_location[2] = e_drone.drone_location[2]
    slope = Float32()
    cos = Float32()
    sin = Float32()
    slope = ((e_drone.setpoint_final[1]-e_drone.drone_location[1])/(e_drone.setpoint_final[0]-e_drone.drone_location[0]))
    cos = np.sqrt(1 + slope**2)
    cos = 1/cos
    sin = np.sqrt(1-cos**2)
    f1 = 0.00005
    f2 = 0.00005

    if e_drone.setpoint_final[0] < e_drone.drone_location[0] and cos > 0:
        cos *= -1
    if e_drone.setpoint_final[1] < e_drone.drone_location[1] and sin > 0:
        sin *= -1

    prev_ranges = [e_drone.laser_negative_latitude, e_drone.laser_positive_longitude, e_drone.laser_negative_longitude]
    while(is_at_setpoint(e_drone.setpoint_final)):
        e_drone.setpoint_location = [e_drone.drone_location[0] + f1*cos, e_drone.drone_location[1]+ f2*sin, e_drone.setpoint_location[2]]

        #If setpoint_location become less or more than setpoint_final
        if ((cos > 0 and e_drone.setpoint_location[0] > e_drone.setpoint_final[0]) or (cos < 0 and e_drone.setpoint_location[0] < e_drone.setpoint_final[0])):
            e_drone.setpoint_location = e_drone.setpoint_final[:-1] + [e_drone.setpoint_location[2]]
            
        if ((sin > 0 and e_drone.setpoint_location[1] > e_drone.setpoint_final[1]) or (sin < 0 and e_drone.setpoint_location[1] < e_drone.setpoint_final[1])):
            e_drone.setpoint_location = e_drone.setpoint_final[:-1] + [e_drone.setpoint_location[2]]
            
        #rospy.loginfo(e_drone.setpoint_location)
        while (is_at_setpoint(e_drone.setpoint_location)):
            if e_drone.laser_negative_latitude <= 10:
                avoid_obstacle(prev_ranges)
            e_drone.pid()
            time.sleep(0.05)
        if e_drone.setpoint_location[:-1] == e_drone.setpoint_final[:-1]:
            break

    #Descending the drone on the setpoint
    e_drone.setpoint_location = e_drone.setpoint_final
    while (is_at_setpoint(e_drone.setpoint_location)):
        e_drone.pid() 
        time.sleep(0.05)

    rospy.loginfo("Reached Desired Position")
    rospy.loginfo(e_drone.setpoint_final)


# main function, it will move the drone at all three points to reach the destination.
def main():

    e_drone.setpoint_final = [19.0007046575, 71.9998955286, 22.15]
    reach_destination()
    #To settle on the destination
    t = time.time()
    while time.time() -t < 10:
        e_drone.pid()
        time.sleep(0.05)

    t = time.time()
    while time.time() -t < 3:
        e_drone.rpyt_cmd.rcRoll = 1500
        e_drone.rpyt_cmd.rcPitch = 1500
        # e_drone.rpyt_cmd.rcYaw = 2000.0
        e_drone.rpyt_cmd.rcThrottle = 1000
        e_drone.rpyt_pub.publish(e_drone.rpyt_cmd)

    gripper_active(1)

    e_drone.setpoint_final = [e_drone.box_position[0], e_drone.box_position[1], e_drone.box_position[2]]
    reach_destination()
    t = time.time()
    while time.time() -t < 10:
        e_drone.pid()
        time.sleep(0.05)

    gripper_active(0)

    e_drone.setpoint_location = [e_drone.box_position[0], e_drone.box_position[1], 13]
    while ((e_drone.drone_location[0] > e_drone.setpoint_location[0]+0.000004517 or e_drone.drone_location[0] < e_drone.setpoint_location[0]-0.000004517) or (e_drone.drone_location[1] >  e_drone.setpoint_location[1]+0.0000047487 or e_drone.drone_location[1] < e_drone.setpoint_location[1]-0.0000047487) or (e_drone.drone_location[2] > e_drone.setpoint_location[2]+0.2 or e_drone.drone_location[2] < e_drone.setpoint_location[2]-0.2)):
        e_drone.pid()
        time.sleep(0.05)
    t = time.time()
    while time.time() -t < 10:
        e_drone.pid()
        time.sleep(0.05)

    while True:
        e_drone.pid()
        time.sleep(0.05) 


if __name__ == '__main__':

    # pause of 4 sec to open and load the gazibo
    t = time.time()
    while time.time() -t < 4:
        pass

    # making e_drone object of Edrone class
    e_drone = Edrone()

    # pause of 1 sec 
    t = time.time()
    while time.time() -t < 1:
        pass

    while not rospy.is_shutdown():
        main()
        break
