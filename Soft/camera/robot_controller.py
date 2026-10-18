import rclpy
from rclpy.node import Node
from std_msgs.msg import Int8MultiArray
import urllib.request
import json

VISION_API_URL = "http://127.0.0.1:5000/status"

class RobotControllerNode(Node):
    def __init__(self):
        super().__init__('robot_controller_node')
        self.publisher_ = self.create_publisher(Int8MultiArray, 'camera/goal', 10)
        self.timer = self.create_timer(0.05, self.timer_callback)
        self.get_logger().info('Node gotowy. Czekam na pierwsza petle...')

    def timer_callback(self):
        try:
            req = urllib.request.Request(VISION_API_URL)
            with urllib.request.urlopen(req, timeout=1.0) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            command = data["command"]
            obstacle = data["obstacle_detected"]
            goal_array = [0, 0, 0, 0, 0]
            
            if obstacle or command == "STOP" or command == "NO_FINGERS":
                goal_array[4] = 1
            elif command == "FORWARD":
                goal_array[0] = 1
            elif command == "BACKWARD":
                goal_array[1] = 1
            elif command == "LEFT":
                goal_array[2] = 1
            elif command == "RIGHT":
                goal_array[3] = 1
                
            msg = Int8MultiArray()
            msg.data = goal_array
            self.publisher_.publish(msg)
            
            # WŁĄCZONY PRINT DO DEBUGOWANIA
            self.get_logger().info(f'Wysylam do ROS: {goal_array} (Gest: {command})')
            
        except Exception as e:
            self.get_logger().warning(f"Blad petli: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = RobotControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()