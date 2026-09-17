FROM ubuntu:22.04 AS champsim-builder

# Optional: use APT mirror for faster builds (e.g., ARG APT_MIRROR=mirrors.ustc.edu.cn)
ARG APT_MIRROR="archive.ubuntu.com"
# Optional: use GitHub mirror for cloning ChampSim (e.g., ARG GIT_BASE=https://gitclone.com/github.com/)
ARG GIT_BASE="https://github.com/"

# Fixed toolchain (pinned versions for reproducibility)
RUN sed -i "s|archive.ubuntu.com|${APT_MIRROR}|g" /etc/apt/sources.list && \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    cmake=3.22.1-1ubuntu1 \
    g++-13=13.2.0-23ubuntu4 \
    gcc-13=13.2.0-23ubuntu4 \
    git=1:2.34.1-1ubuntu1.12 \
    wget=1.21.2-2ubuntu1 \
    xz-utils \
    python3=3.10.12-1~22.04 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 100 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 100

# Clone ChampSim at fixed commit (supports GIT_BASE mirror)
WORKDIR /opt
RUN git clone ${GIT_BASE}ChampSim/ChampSim.git && \
    cd ChampSim && \
    git checkout 51588e1d6f97875fe8de1a3621d28668bff83fcf && \
    git submodule update --init && \
    ./vcpkg/bootstrap-vcpkg.sh && \
    ./vcpkg/vcpkg install

# Env vars for ChampSim builds
ENV CXXFLAGS="-O3 -std=c++17 -fno-exceptions -fno-rtti"

# Pre-build LRU baseline (caches build artifacts)
RUN cd /opt/ChampSim && \
    python3 config.sh config/my_policy_config.json && \
    mkdir -p config && \
    echo '{"executable_name":"champsim","block_size":64,"page_size":4096,"heartbeat_frequency":10000000,"num_cores":1,"ooo_cpu":[{"frequency":4000,"ifetch_buffer_size":64,"decode_buffer_size":32,"dispatch_buffer_size":32,"register_file_size":128,"rob_size":352,"lq_size":128,"sq_size":72,"fetch_width":6,"decode_width":6,"dispatch_width":6,"execute_width":4,"lq_width":2,"sq_width":2,"retire_width":5,"mispredict_penalty":1,"scheduler_size":128,"decode_latency":1,"dispatch_latency":1,"schedule_latency":0,"execute_latency":0,"branch_predictor":"bimodal","btb":"basic_btb"}],"L1I":{"sets":64,"ways":8,"rq_size":64,"wq_size":64,"pq_size":8,"mshr_size":8,"latency":4,"max_tag_check":2,"max_fill":2},"L1D":{"sets":64,"ways":12,"rq_size":64,"wq_size":64,"pq_size":8,"mshr_size":16,"latency":5,"max_tag_check":2,"max_fill":2,"prefetch_as_load":false,"virtual_prefetch":false,"replacement":"lru"},"L2C":{"sets":1024,"ways":8,"rq_size":32,"wq_size":32,"pq_size":16,"mshr_size":32,"latency":10,"max_tag_check":1,"max_fill":1,"prefetch_as_load":false,"virtual_prefetch":false,"replacement":"lru"},"LLC":{"sets":2048,"ways":16,"rq_size":32,"wq_size":32,"pq_size":32,"mshr_size":64,"latency":20,"max_tag_check":1,"max_fill":1,"prefetch_as_load":false,"virtual_prefetch":false,"replacement":"lru"}}' > config/lru_baseline.json && \
    python3 config.sh config/lru_baseline.json && \
    make -j4

# Build the my_policy module as well
RUN cd /opt/ChampSim && \
    echo '{"executable_name":"champsim","block_size":64,"page_size":4096,"heartbeat_frequency":10000000,"num_cores":1,"ooo_cpu":[{"frequency":4000,"ifetch_buffer_size":64,"decode_buffer_size":32,"dispatch_buffer_size":32,"register_file_size":128,"rob_size":352,"lq_size":128,"sq_size":72,"fetch_width":6,"decode_width":6,"dispatch_width":6,"execute_width":4,"lq_width":2,"sq_width":2,"retire_width":5,"mispredict_penalty":1,"scheduler_size":128,"decode_latency":1,"dispatch_latency":1,"schedule_latency":0,"execute_latency":0,"branch_predictor":"bimodal","btb":"basic_btb"}],"L1I":{"sets":64,"ways":8,"rq_size":64,"wq_size":64,"pq_size":8,"mshr_size":8,"latency":4,"max_tag_check":2,"max_fill":2},"L1D":{"sets":64,"ways":12,"rq_size":64,"wq_size":64,"pq_size":8,"mshr_size":16,"latency":5,"max_tag_check":2,"max_fill":2,"prefetch_as_load":false,"virtual_prefetch":false,"replacement":"my_policy"},"L2C":{"sets":1024,"ways":8,"rq_size":32,"wq_size":32,"pq_size":16,"mshr_size":32,"latency":10,"max_tag_check":1,"max_fill":1,"prefetch_as_load":false,"virtual_prefetch":false,"replacement":"my_policy"},"LLC":{"sets":2048,"ways":16,"rq_size":32,"wq_size":32,"pq_size":32,"mshr_size":64,"latency":20,"max_tag_check":1,"max_fill":1,"prefetch_as_load":false,"virtual_prefetch":false,"replacement":"my_policy"}}' > config/my_policy_config.json && \
    python3 config.sh config/my_policy_config.json && \
    make -j4

# Record environment versions
RUN echo "gcc: $(gcc --version | head -1)" > /opt/champsim.env && \
    echo "cmake: $(cmake --version | head -1)" >> /opt/champsim.env && \
    echo "python: $(python3 --version)" >> /opt/champsim.env && \
    echo "champsim: $(cd /opt/ChampSim && git rev-parse HEAD)" >> /opt/champsim.env

# ── Evaluation stage ──
FROM ubuntu:22.04
ARG APT_MIRROR="archive.ubuntu.com"
RUN sed -i "s|archive.ubuntu.com|${APT_MIRROR}|g" /etc/apt/sources.list && \
    apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3=3.10.12-1~22.04 \
    python3-pip \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=champsim-builder /opt/ChampSim /opt/ChampSim
COPY --from=champsim-builder /opt/champsim.env /opt/champsim.env

RUN pip3 install --no-cache-dir pyyaml

WORKDIR /benchmark
COPY . .

# Symlink ChampSim
RUN ln -s /opt/ChampSim data/ChampSim

# Download traces (continue on error)
RUN bash data/download_traces.sh 2>/dev/null; exit 0

# Generate baseline IPC
RUN python3 verification/evaluator.py replacement/my_policy.cc --mode quick --metrics-out /tmp/init_check.json 2>/dev/null; exit 0

CMD ["python3", "verification/evaluator.py", "replacement/my_policy.cc", "--mode", "full"]
