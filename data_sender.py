from triad_openvr import triad_openvr
from triad_openvr.triad_openvr import matrix_to_flat_list
import time
import sys

import socket
import struct
import time
import random
import numpy as np
# --- 配置 ---
UBUNTU_IP = "192.168.20.152"  # 接收端Ubuntu的IP地址，请务必修改
PORT = 9999                 # 端口号，必须与接收端一致
NUM_FLOATS = 36             # 要发送的浮点数数量

# 创建一个UDP socket
# AF_INET 表示使用 IPv4
# SOCK_DGRAM 表示使用 UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print(f"开始向 {UBUNTU_IP}:{PORT} 发送数据...")

# 使用 'f' 代表一个4字节的单精度浮点数。'21f' 表示21个浮点数。
# '<' 表示使用小端字节序（在x86架构的Windows和Ubuntu上是默认的，显式指定更具兼容性）
format_string = f'<{NUM_FLOATS}f'
v = triad_openvr.triad_openvr()
v.print_discovered_objects()


# while True:
#     txt = ""
#     print("________________")
    
#     try:
#         for each in v.devices["tracker_0"].get_pose_euler():
#             txt += f"{each:0.3f} "
#             txt += " "
#         print("\r" + txt, end = " ")
        
#     except Exception as e:
#         print("Error:", e)
#     try:
#         for each in v.devices["tracker_1"].get_pose_euler():
#             txt += f"{each:0.3f} "
#             txt += " "
#         print("\r" + txt, end = " ")
#     except Exception as e:
#         print("Error:", e)
#     try:
#         for each in v.devices["tracker_2"].get_pose_euler():
#             txt += f"{each:0.3f} "
#             txt += " "
#         print("\r" + txt, end = " ")
#     except Exception as e:
#         print("Error:", e)
    
#     print("________________")

#     time.sleep(0.01)
    
print("sending vive data...")    

try:
    i = 0
    time_last_sending = time.time()
    while True:
        data_to_send = []
        zero_pad = [0.,0.,0.,0.,0.,0.,0.,0.,0.,0.,0.,0.]  # 用于填充的零值列表
        valid_data = False
        try:
            # data_to_send.extend(v.devices["tracker_0"].get_pose_quaternion_robust())
            # data_to_send.extend(v.devices["tracker_0"].get_pose_quaternion_tfs())
            get_pose_matrix = v.devices["tracker_0"].get_pose_matrix()
            data_to_send.extend(matrix_to_flat_list(get_pose_matrix))
            valid_data = True
        except Exception as e:
            # print("tracker_0 error:", e)
            data_to_send.extend(zero_pad)
        try:
            # data_to_send.extend(v.devices["tracker_1"].get_pose_quaternion_tfs())
            # print(np.array(data_to_send) - np.array((v.devices["tracker_1"].get_pose_quaternion_tfs())))
            get_pose_matrix = v.devices["tracker_1"].get_pose_matrix()
            data_to_send.extend(matrix_to_flat_list(get_pose_matrix))
            valid_data = True
        except Exception as e:
            print("tracker_1 error:", e)
            data_to_send.extend(zero_pad)
        try:
            # data_to_send.extend(v.devices["tracker_2"].get_pose_quaternion_tfs())
            get_pose_matrix = v.devices["tracker_2"].get_pose_matrix()
            data_to_send.extend(matrix_to_flat_list(get_pose_matrix))
            valid_data = True
        except Exception as e:
            # print("tracker_2 error:", e)
            data_to_send.extend(zero_pad)
        
        i += 1
        if i % 10 == 0 and valid_data:
            # print(data_to_send)
            print(np.array(data_to_send[12:24])[0:3])
            print()
            print(np.array(data_to_send[12:24])[3:].reshape(3,3))
            print()
        if not valid_data and (time.time() - time_last_sending) < 0.01:
            continue
        time_last_sending = time.time()
        # data_to_send = [random.random() * 100 for _ in range(NUM_FLOATS)]
        
        # 2. 使用struct将浮点数列表打包成二进制数据
        #    `*data_to_send` 将列表解包为独立的参数传给pack函数
        # print(data_to_send)
        packed_data = struct.pack(format_string, *data_to_send)
        
        # 3. 发送数据
        sock.sendto(packed_data, (UBUNTU_IP, PORT))
        
        # 打印部分数据用于观察
        # print(f"已发送: [{data_to_send[0]:.2f}, {data_to_send[1]:.2f}, ...], 大小: {len(packed_data)} 字节")
        
        # 控制发送速率，例如每秒发送100次 (100Hz)
        # 如果想尽可能快地发送，可以移除或减小sleep的时间
        time.sleep(1e-4)
        # print(time.time())

except KeyboardInterrupt:
    print("\n程序停止。")
finally:
    # 关闭socket
    sock.close()
    print("Socket已关闭。")