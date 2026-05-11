import asyncio
import logging
from threading import Thread

logger = logging.getLogger(__name__)

try:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class Ros2Runtime:
    """Manages rclpy lifecycle: init, spin thread, shutdown."""

    def __init__(self, node_name: str = "robot_control_backend", domain_id: int = 0):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed. Install ROS2 to use real mode.")
        self._node_name = node_name
        self._domain_id = domain_id
        self._node: Node | None = None
        self._spin_thread: Thread | None = None
        self._executor: SingleThreadedExecutor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop):
        """Initialize rclpy, create node, start spin thread. Call on FastAPI startup."""
        self._loop = loop
        rclpy.init(domain_id=self._domain_id)
        self._node = Node(self._node_name)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()
        logger.info("Ros2Runtime started: node=%s, domain_id=%d", self._node_name, self._domain_id)

    def stop(self):
        """Stop spin thread, destroy node, shutdown rclpy. Call on FastAPI shutdown."""
        if self._executor:
            self._executor.shutdown()
            self._executor = None
        if self._node:
            self._node.destroy_node()
            self._node = None
        if rclpy.ok():
            rclpy.shutdown()
        self._loop = None
        self._spin_thread = None
        logger.info("Ros2Runtime stopped")

    @property
    def node(self) -> Node:
        if self._node is None:
            raise RuntimeError("Ros2Runtime not started")
        return self._node

    @property
    def is_running(self) -> bool:
        return self._node is not None

    def call_async_in_loop(self, coro):
        """Call an asyncio coroutine from rclpy callback thread safely."""
        if self._loop is None or self._loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=5.0)
        except Exception:
            logger.exception("Failed to execute async callback")
