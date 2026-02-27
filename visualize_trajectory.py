#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIVE Tracker Trajectory Analysis
功能：
1. 接收 UDP 数据包
2. 记录指定 Tracker 的运动轨迹
3. 使用 Matplotlib 进行离线 3D 轨迹绘制和直线拟合分析
4. 输出误差统计指标
"""

import socket
import struct
import threading
import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import sys


class VIVEDataReceiver:
    """
    UDP数据接收器模块
    负责后台接收数据并维护最新的一帧数据
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9999, num_floats: int = 36):
        self.host = host
        self.port = port
        self.num_floats = num_floats

        self.format_string = f"<{self.num_floats}f"
        self.buffer_size = struct.calcsize(self.format_string)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        
        self.latest_data = None
        self.latest_addr = None
        self.packet_count = 0
        self.lock = threading.Lock()

        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        print(f"[Receiver] Listening on {self.host}:{self.port} ...")

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        print("[Receiver] Stopped.")

    def _recv_loop(self):
        while self._running:
            try:
                data, addr = self.sock.recvfrom(self.buffer_size * 2)
                if len(data) != self.buffer_size:
                    continue
                
                floats = struct.unpack(self.format_string, data)
                arr = np.asarray(floats, dtype=np.float32)
                
                with self.lock:
                    self.latest_data = arr
                    self.latest_addr = addr
                    self.packet_count += 1
                    
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                print(f"[Receiver] Error: {e}")
                continue

    def get_latest_data(self):
        with self.lock:
            if self.latest_data is None:
                return None, None, 0
            return self.latest_data.copy(), self.latest_addr, self.packet_count

def fit_line_3d(points):
    """
    使用 SVD 拟合 3D 直线
    :param points: (N, 3) 数组
    :return: 
        line_point: 直线上的一个点 (重心)
        line_dir: 直线方向向量
        residuals: 每个点到直线的距离
    """
    # 1. 计算重心
    datamean = points.mean(axis=0)
    
    # 2. 去中心化
    centered_data = points - datamean
    
    # 3. SVD 分解
    try:
        _, _, vv = np.linalg.svd(centered_data)
        line_dir = vv[0]
    except np.linalg.LinAlgError:
        print("SVD failed, using default direction.")
        line_dir = np.array([1.0, 0.0, 0.0])

    # 4. 计算每个点在直线上的投影点
    t = np.dot(centered_data, line_dir)
    
    # 投影点
    projected_points = datamean + np.outer(t, line_dir)
    
    # 5. 计算残差 (距离)
    residuals = np.linalg.norm(points - projected_points, axis=1)
    
    return datamean, line_dir, residuals, projected_points

def main():
    # --- 配置 ---
    BIND_IP = "0.0.0.0"
    PORT = 9999
    NUM_FLOATS = 36
    
    receiver = VIVEDataReceiver(host=BIND_IP, port=PORT, num_floats=NUM_FLOATS)
    receiver.start()
    
    try:
        # 等待数据流稳定
        print("Waiting for data stream...")
        while True:
            data, _, _ = receiver.get_latest_data()
            if data is not None:
                break
            time.sleep(0.1)
        print("Data stream detected.")

        tracker_id = 1
        
        print(f"\nTarget Tracker: {tracker_id}")
        input(f"Press [Enter] to START recording trajectory for Tracker {tracker_id}...")
        
        print("Recording... (Press Ctrl+C to stop recording and analyze)")
        
        recorded_points = []
        start_time = time.time()
        
        try:
            while True:
                data, _, _ = receiver.get_latest_data()
                if data is not None:
                    # 提取对应 tracker 的数据
                    start_idx = tracker_id * 12
                    end_idx = start_idx + 12
                    
                    if end_idx <= len(data):
                        tracker_data = data[start_idx:end_idx]
                        # 检查有效性 (非全0)
                        if not np.all(np.abs(tracker_data) < 1e-6):
                            pos = tracker_data[0:3]
                            recorded_points.append(pos)
                            sys.stdout.write(f"\rRecorded {len(recorded_points)} points")
                            sys.stdout.flush()
                
                time.sleep(0.01) # 100Hz 采样
        except KeyboardInterrupt:
            print("\nRecording stopped by user.")
        
        if len(recorded_points) < 2:
            print("Not enough points recorded for analysis.")
            return

        points = np.array(recorded_points)
        print(f"\nAnalyzing {len(points)} points...")
        
        # --- 拟合与分析 ---
        line_point, line_dir, residuals, projected_points = fit_line_3d(points)
        
        mean_error = np.mean(residuals)
        max_error = np.max(residuals)
        std_error = np.std(residuals)
        rmse = np.sqrt(np.mean(residuals**2))
        
        print("-" * 40)
        print(f"Analysis Results for Tracker {tracker_id}:")
        print(f"  Sample Count: {len(points)}")
        print(f"  Line Direction: [{line_dir[0]:.4f}, {line_dir[1]:.4f}, {line_dir[2]:.4f}]")
        print(f"  Mean Error: {mean_error*1000:.4f} mm")
        print(f"  Max Error:  {max_error*1000:.4f} mm")
        print(f"  Std Dev:    {std_error*1000:.4f} mm")
        print(f"  RMSE:       {rmse*1000:.4f} mm")
        print("-" * 40)
        
        # --- 绘图 ---
        print("Generating plot...")
        fig = plt.figure(figsize=(12, 6))
        
        # 3D 轨迹图
        ax = fig.add_subplot(121, projection='3d')
        ax.set_title(f"3D Trajectory & Fitted Line (Tracker {tracker_id})")
        
        # 原始点
        ax.scatter(points[:, 0], points[:, 1], points[:, 2], c='b', marker='.', s=1, alpha=0.5, label='Raw Data')
        
        # 拟合直线 
        t_vals = np.dot(projected_points - line_point, line_dir)
        t_min, t_max = np.min(t_vals), np.max(t_vals)

        # 稍微延长一点以便观察
        margin = (t_max - t_min) * 0.1
        p_start_ext = line_point + (t_min - margin) * line_dir
        p_end_ext = line_point + (t_max + margin) * line_dir
        
        line_pts = np.vstack([p_start_ext, p_end_ext])
        ax.plot(line_pts[:, 0], line_pts[:, 1], line_pts[:, 2], 'r-', linewidth=2, label='Fitted Line')
        
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.set_zlabel('Z (m)')
        ax.legend()

        # --- 设置等比例坐标轴 ---
        # 获取当前数据的最大范围，以保持真实的物理比例
        x_limits = [points[:, 0].min(), points[:, 0].max()]
        y_limits = [points[:, 1].min(), points[:, 1].max()]
        z_limits = [points[:, 2].min(), points[:, 2].max()]
        
        x_range = x_limits[1] - x_limits[0]
        y_range = y_limits[1] - y_limits[0]
        z_range = z_limits[1] - z_limits[0]
        
        max_range = max(x_range, y_range, z_range)
        
        mid_x = np.mean(x_limits)
        mid_y = np.mean(y_limits)
        mid_z = np.mean(z_limits)
        
        ax.set_xlim(mid_x - max_range/2, mid_x + max_range/2)
        ax.set_ylim(mid_y - max_range/2, mid_y + max_range/2)
        ax.set_zlim(mid_z - max_range/2, mid_z + max_range/2)
        # -------------------------------
        
        # 误差分布图
        ax2 = fig.add_subplot(122)
        ax2.set_title("Distance to Line (Error) Distribution")
        ax2.plot(residuals * 1000, 'g-', alpha=0.7)
        ax2.set_xlabel('Sample Index')
        ax2.set_ylabel('Error (mm)')
        ax2.grid(True)
        
        # 在图上标注统计信息
        stats_text = (
            f"Mean: {mean_error*1000:.2f} mm\n"
            f"Max:  {max_error*1000:.2f} mm\n"
            f"Std:  {std_error*1000:.2f} mm"
        )
        ax2.text(0.05, 0.95, stats_text, transform=ax2.transAxes, 
                 verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        plt.show()
        
        # 保存数据提示
        save_opt = input("Save trajectory data? (y/N): ").strip().lower()
        if save_opt == 'y':
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trajectory_tracker{tracker_id}_{timestamp}.csv"
            
            # 保存为 CSV，包含表头
            np.savetxt(filename, points, delimiter=",", header="x,y,z", comments="")
            print(f"Saved to {filename}")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        receiver.stop()

if __name__ == "__main__":
    main()
