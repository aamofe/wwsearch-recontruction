#!/bin/bash
set -e 

# ==============================================================================
# 阶段 0: 容器持久化逻辑
# ==============================================================================
CONTAINER_NAME="ww"
# 强制指定 Ubuntu 18.04 镜像以确保基础 OS 环境一致
IMAGE_NAME="ubuntu:18.04"
ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)

echo "--- 阶段 0: 检查 Docker 及容器状态 ---"

# 智能跳过 Docker 安装
if ! command -v docker > /dev/null 2>&1; then
    echo "未检测到 Docker，正在安装..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
else
    echo "Docker 已就绪。"
fi

if [ "$(sudo docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    if [ "$(sudo docker ps -aq -f status=exited -f name=^/${CONTAINER_NAME}$)" ]; then
        echo "容器已存在但处于停止状态，正在启动..."
        sudo docker start ${CONTAINER_NAME}
    else
        echo "容器 ${CONTAINER_NAME} 正在运行中。"
    fi
else
    echo "创建新容器: ${CONTAINER_NAME} (Ubuntu 18.04)..."
    sudo docker run -d --name ${CONTAINER_NAME} \
        -v "$ROOT_DIR":/work \
        -w /work \
        ${IMAGE_NAME} sleep infinity
fi

docker_exec="sudo docker exec ${CONTAINER_NAME}"

# ==============================================================================
# 第一阶段: 环境增量更新 (对齐基准环境)
# ==============================================================================
echo "--- 第一阶段: 检查并安装基准依赖 ---"

if ! $docker_exec which wget > /dev/null 2>&1; then
    echo "正在初始化容器环境 (Ubuntu 18.04)..."
    $docker_exec apt-get update
    # 安装 GCC (18.04 默认 GCC 7.x > 4.9.3，满足 C++11 要求)
    # 安装 RocksDB 和 Snappy 编译所需的依赖库
    $docker_exec apt-get install -y \
        build-essential \
        gcc \
        g++ \
        cmake \
        git \
        curl \
        wget \
        libgflags-dev \
        libbz2-dev \
        liblz4-dev \
        libzstd-dev \
        zlib1g-dev \
        python3 \
        python3-pip \
        python3-venv
else
    echo "容器基础依赖已就绪。"
fi

# ==============================================================================
# 第二阶段: 第三方库路径配置 (对齐内嵌版本)
# ==============================================================================
echo "--- 第二阶段: 配置内嵌库路径 (Protobuf 2.4.1 / RocksDB v5.16.6) ---"

# 这里的路径根据你项目的实际结构调整，假设在 wwsearch/third_party 下
PROTOBUF_LIB="/work/wwsearch/third_party/protobuf/lib"
ROCKSDB_LIB="/work/wwsearch/third_party/rocksdb"
SNAPPY_LIB="/work/wwsearch/third_party/snappy"

# 注入动态库路径并刷新 ldconfig，确保运行时优先链接内嵌版本
$docker_exec bash -c "echo '$PROTOBUF_LIB' > /etc/ld.so.conf.d/wwsearch.conf"
$docker_exec bash -c "echo '$ROCKSDB_LIB' >> /etc/ld.so.conf.d/wwsearch.conf"
$docker_exec bash -c "echo '$SNAPPY_LIB' >> /etc/ld.so.conf.d/wwsearch.conf"
$docker_exec ldconfig

# ==============================================================================
# 第三阶段: Python 环境 (3.6+)
# ==============================================================================
# ==============================================================================
# 第三阶段: Python 环境 (3.6+)
# ==============================================================================
echo "--- 第三阶段: 检查 Python 虚拟环境 ---"

VENV_DIR="/work/venv"

# 检查 venv 模块是否真的可用，不可用则补装
if ! $docker_exec dpkg -l | grep -q "python3-venv"; then
    echo "补装 python3-venv 软件包..."
    $docker_exec apt-get update
    $docker_exec apt-get install -y python3-venv
fi

if ! $docker_exec [ -d "$VENV_DIR" ]; then
    echo "创建 Python 3.6+ 虚拟环境..."
    # 彻底删除可能存在的残余文件夹
    $docker_exec rm -rf $VENV_DIR
    $docker_exec python3 -m venv $VENV_DIR
    $docker_exec $VENV_DIR/bin/pip install --upgrade pip
else
    # 如果目录存在但没有 pip (创建失败的残余)，也重新触发一次
    if ! $docker_exec [ -f "$VENV_DIR/bin/pip" ]; then
        echo "检测到残余虚拟环境，正在修复..."
        $docker_exec rm -rf $VENV_DIR
        $docker_exec python3 -m venv $VENV_DIR
    fi
    echo "虚拟环境已就绪。"
fi

# ==============================================================================
# 最终验证
# ==============================================================================
echo "--- 环境一致性检查 ---"
echo -n "操作系统: " && $docker_exec cat /etc/issue | head -n 1
echo -n "编译器 (GCC >= 4.9.3): " && $docker_exec gcc --version | head -n 1
echo -n "Python (3.6+): " && $docker_exec python3 --version

echo "===================================================="
echo "状态: 已完全对齐基准环境说明"
echo "容器: ${CONTAINER_NAME}"
echo "项目路径: /work"
echo "===================================================="