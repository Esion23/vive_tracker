#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIVE Tracker 6D Pose Visualization using PyVista
功能：接收 UDP 数据包，使用 PyVista 实时可视化 VIVE Tracker 的 6D 姿态
"""

import os
import sys

os.environ["VTK_DISABLE_EGL"] = "1"
os.environ["VTK_USE_X"] = "1"


import socket
import struct
import threading
from typing import Optional, Tuple
import numpy as np
import pyvista as pv

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
        
        self.latest_data: Optional[np.ndarray] = None
        self.latest_addr = None
        self.packet_count = 0
        self.lock = threading.Lock()

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        print(f"[Receiver] 正在监听 {self.host}:{self.port} ...")

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        print("[Receiver] 已停止。")

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

    def get_latest_data(self) -> Tuple[Optional[np.ndarray], any, int]:
        with self.lock:
            if self.latest_data is None:
                return None, None, 0
            return self.latest_data.copy(), self.latest_addr, self.packet_count


class VIVEVisualizer:
    """
    可视化模块
    使用 PyVista 显示 3D 场景和 Tracker 姿态
    """
    def __init__(self, receiver: VIVEDataReceiver, num_trackers: int = 3):
        self.receiver = receiver
        self.num_trackers = num_trackers

        self.visible_trackers = [1, 2] # 默认显示 Tracker 1 和 2
        try:
            self.plotter = pv.Plotter(window_size=[1024, 768], title="VIVE Tracker 6D Pose Visualization")
        except Exception as e:
            print(f"[Visualizer] 初始化失败: {e}")
            sys.exit(1)
        
        # 设置背景和相机
        self.plotter.set_background("black")
        self.plotter.add_axes()
        self.plotter.show_grid()
        self.plotter.camera.position = (2, 2, 2)
        self.plotter.camera.focal_point = (0, 0, 0)
        self.plotter.camera.up = (0, 1, 0)

        # 创建 Trackers 的几何体 (Actor)
        self.tracker_actors = []
        
        for i in range(num_trackers):
            # 创建一个RGB坐标系模型 
            # 红色 X 轴
            arrow_x = pv.Arrow(start=(0,0,0), direction=(1,0,0), scale=0.2)
            arrow_x.point_data['RGB'] = np.tile([255, 0, 0], (arrow_x.n_points, 1))
            # 绿色 Y 轴
            arrow_y = pv.Arrow(start=(0,0,0), direction=(0,1,0), scale=0.2)
            arrow_y.point_data['RGB'] = np.tile([0, 255, 0], (arrow_y.n_points, 1))
            # 蓝色 Z 轴
            arrow_z = pv.Arrow(start=(0,0,0), direction=(0,0,1), scale=0.2)
            arrow_z.point_data['RGB'] = np.tile([0, 0, 255], (arrow_z.n_points, 1))
            
            tracker_mesh = arrow_x + arrow_y + arrow_z
            
            # 根据配置决定是否显示
            is_visible = (i in self.visible_trackers)
            
            # 注意：add_mesh 返回 actor，我们可以控制 visibility
            actor = self.plotter.add_mesh(tracker_mesh, scalars='RGB', rgb=True, show_scalar_bar=False, label=f"Tracker {i}")
            actor.SetVisibility(is_visible)
            
            self.tracker_actors.append(actor)

        self.tracker_labels = []
        self.label_polydatas = []
        
        for i in range(num_trackers):
             # 手动创建 PolyData
             poly = pv.PolyData([[0.0, 0.0, 0.0]])
             # 添加标签数据
             poly["labels"] = [f"Tracker {i}"]
             self.label_polydatas.append(poly)
             
             # 根据配置决定是否显示
             is_visible = (i in self.visible_trackers)
             
             # add_point_labels 可以接受 PolyData
             label_actor = self.plotter.add_point_labels(
                 poly, 
                 "labels",
                 point_size=0,
                 font_size=20,
                 text_color="white",
                 always_visible=True
             )
             label_actor.SetVisibility(is_visible)
             self.tracker_labels.append(label_actor)

        # 添加一个固定的世界坐标系作为参考
        self.plotter.add_axes(interactive=False)
        self.plotter.add_text("World Origin", position='upper_left', font_size=10)
        
        # 绘制世界坐标系原点 (RGB轴)
        origin_x = pv.Arrow(start=(0,0,0), direction=(1,0,0), scale=0.5)
        origin_x.point_data['RGB'] = np.tile([255, 0, 0], (origin_x.n_points, 1))
        
        origin_y = pv.Arrow(start=(0,0,0), direction=(0,1,0), scale=0.5)
        origin_y.point_data['RGB'] = np.tile([0, 255, 0], (origin_y.n_points, 1))
        
        origin_z = pv.Arrow(start=(0,0,0), direction=(0,0,1), scale=0.5)
        origin_z.point_data['RGB'] = np.tile([0, 0, 255], (origin_z.n_points, 1))
        
        origin_mesh = origin_x + origin_y + origin_z
        self.plotter.add_mesh(origin_mesh, scalars='RGB', rgb=True, show_scalar_bar=False, opacity=0.5)


        self.coord_text_actor = self.plotter.add_text(
            "Tracker: Waiting for data...", 
            position=(10, 10),
            font_size=12, 
            color='white',
            shadow=True
        )
        
        # 添加地面网格作为参考平面
        ground = pv.Plane(center=(0, 0, 0), direction=(0, 1, 0), i_size=5, j_size=5)
        self.plotter.add_mesh(ground, color='gray', opacity=0.3, show_edges=True)
        
        print("[Visualizer] 初始化完成")

    def update(self):
        """
        更新一帧画面
        """
        data, _, _ = self.receiver.get_latest_data()
        
        if data is not None:
            # 用于存储每个 Tracker 的状态文本
            tracker_status_texts = {}
            for i in self.visible_trackers:
                tracker_status_texts[i] = "N/A"
            
            for i in range(self.num_trackers):
                # 提取对应 tracker 的数据 (12 floats)
                start_idx = i * 12
                end_idx = start_idx + 12
                if end_idx > len(data):
                    break
                    
                tracker_data = data[start_idx:end_idx]
                
                # 检查是否全0 (无效数据)
                if np.all(np.abs(tracker_data) < 1e-6):
                    if i in self.visible_trackers:
                        tracker_status_texts[i] = "Disconnected"
                    continue
                    
                pos = tracker_data[0:3]
                rot = tracker_data[3:12].reshape(3, 3)
                
                # 更新坐标显示字符串
                if i in self.visible_trackers:
                    tracker_status_texts[i] = f"Pos: ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})"
                
                mat4x4 = np.eye(4)
                mat4x4[:3, :3] = rot
                mat4x4[:3, 3] = pos

                # 只更新可见的 Tracker
                if i in self.visible_trackers:
                    self.tracker_actors[i].user_matrix = mat4x4
                    if i < len(self.label_polydatas):
                        label_pos = pos + np.array([0.05, 0.05, 0.05])
                        self.label_polydatas[i].points[0] = label_pos
            
            # 更新右下角文本
            if self.coord_text_actor:
                status_str = "\n".join([f"Tracker {k}: {v}" for k, v in sorted(tracker_status_texts.items())])
                self.coord_text_actor.SetInput(status_str)

    def run(self):
        """
        启动可视化循环
        """
        print("[Visualizer] 启动渲染循环...")

        self.plotter.show(interactive_update=True)
        
        while True:
            self.update()
            self.plotter.update()

            try:
                if self.plotter.render_window.GetGenericWindowId() == 0: 
                   break 
            except:
                break


def main():
    # 配置
    BIND_IP = "0.0.0.0"
    PORT = 9999
    NUM_FLOATS = 36
    
    # 1. 启动接收器
    receiver = VIVEDataReceiver(host=BIND_IP, port=PORT, num_floats=NUM_FLOATS)
    receiver.start()
    
    try:
        # 2. 启动可视化
        visualizer = VIVEVisualizer(receiver, num_trackers=3)
        visualizer.run()
        
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")
    finally:
        receiver.stop()

if __name__ == "__main__":
    main()
