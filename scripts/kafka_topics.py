#!/usr/bin/env python3
"""
Kafka Topic Management Script for Real-Time E-Commerce Analytics Pipeline.

This script provides utilities for creating, listing, and managing Kafka topics
using the Redpanda rpk command-line tool.
"""

import subprocess
import sys
import time
from typing import List, Dict, Any


class KafkaTopicManager:
    """Manages Kafka topics for the e-commerce analytics pipeline."""

    def __init__(self, container_name: str = "ecommerce-redpanda"):
        """
        Initialize the topic manager.

        Args:
            container_name: Name of the Redpanda Docker container
        """
        self.container_name = container_name
        self.topics_config = [
            {
                "name": "page_views",
                "partitions": 2,
                "retention": "1h",
                "description": "User page view events"
            },
            {
                "name": "cart_events",
                "partitions": 2,
                "retention": "1h",
                "description": "Cart add/remove events"
            },
            {
                "name": "purchases",
                "partitions": 2,
                "retention": "1h",
                "description": "Purchase completion events"
            }
        ]

    def run_rpk_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """
        Run an rpk command in the Redpanda container.

        Args:
            command: rpk command arguments

        Returns:
            CompletedProcess with command results
        """
        full_command = ["docker", "exec", self.container_name, "rpk"] + command
        return subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            check=False
        )

    def wait_for_redpanda(self, timeout: int = 60) -> bool:
        """
        Wait for Redpanda to be ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if Redpanda is ready, False otherwise
        """
        print("Waiting for Redpanda to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = self.run_rpk_command(["cluster", "info"])
            if result.returncode == 0:
                print("✅ Redpanda is ready!")
                return True

            print(f"Waiting... ({int(timeout - (time.time() - start_time))}s remaining)")
            time.sleep(5)

        print("❌ Redpanda failed to start within timeout")
        return False

    def create_topic(
        self,
        name: str,
        partitions: int = 2,
        retention: str = "1h"
    ) -> bool:
        """
        Create a Kafka topic.

        Args:
            name: Topic name
            partitions: Number of partitions
            retention: Retention time (e.g., "1h", "24h")

        Returns:
            True if successful, False otherwise
        """
        print(f"Creating topic: {name} (partitions: {partitions}, retention: {retention})")

        command = [
            "topic", "create", name,
            "--partitions", str(partitions),
            "--replicas", "1",
            "--config", f"retention.time={retention}",
            "--config", "cleanup.policy=delete",
            "--config", "compression.type=snappy"
        ]

        result = self.run_rpk_command(command)

        if result.returncode == 0:
            print(f"✅ Topic '{name}' created successfully")
            return True
        else:
            print(f"❌ Failed to create topic '{name}': {result.stderr}")
            return False

    def list_topics(self) -> List[str]:
        """
        List all Kafka topics.

        Returns:
            List of topic names
        """
        result = self.run_rpk_command(["topic", "list"])

        if result.returncode == 0:
            topics = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            return topics
        else:
            print(f"❌ Failed to list topics: {result.stderr}")
            return []

    def describe_topic(self, name: str) -> Dict[str, Any]:
        """
        Describe a Kafka topic.

        Args:
            name: Topic name

        Returns:
            Dictionary with topic information
        """
        result = self.run_rpk_command(["topic", "describe", name])

        if result.returncode == 0:
            # Parse the output (simplified parsing)
            lines = result.stdout.strip().split('\n')
            info = {"name": name, "config": {}}

            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    info["config"][key] = value

            return info
        else:
            print(f"❌ Failed to describe topic '{name}': {result.stderr}")
            return {}

    def consume_messages(self, topic: str, num_messages: int = 1) -> None:
        """
        Consume messages from a topic for testing.

        Args:
            topic: Topic name
            num_messages: Number of messages to consume
        """
        print(f"Consuming {num_messages} message(s) from topic '{topic}'...")

        command = ["topic", "consume", topic, "--num", str(num_messages)]
        result = self.run_rpk_command(command)

        if result.returncode == 0:
            print("Messages:")
            print(result.stdout)
        else:
            print(f"❌ Failed to consume from topic '{topic}': {result.stderr}")

    def setup_all_topics(self) -> bool:
        """
        Create all required topics for the pipeline.

        Returns:
            True if all topics created successfully
        """
        print("Setting up Kafka topics for E-Commerce Analytics Pipeline...")
        print()

        # Wait for Redpanda
        if not self.wait_for_redpanda():
            return False

        print("Creating topics...")
        print()

        success_count = 0
        for topic_config in self.topics_config:
            if self.create_topic(
                topic_config["name"],
                topic_config["partitions"],
                topic_config["retention"]
            ):
                success_count += 1
            print()

        print("Verifying topic creation...")
        topics = self.list_topics()
        print(f"Available topics: {topics}")
        print()

        # Verify all expected topics exist
        expected_topics = {config["name"] for config in self.topics_config}
        actual_topics = set(topics)

        if expected_topics.issubset(actual_topics):
            print("✅ All required topics created successfully!")
            print()
            print("Topic details:")
            for topic_config in self.topics_config:
                info = self.describe_topic(topic_config["name"])
                if info:
                    print(f"  {topic_config['name']}: {topic_config['description']}")
                    print(f"    Partitions: {info['config'].get('partition-count', 'N/A')}")
                    print(f"    Retention: {info['config'].get('retention.time', 'N/A')}")
            print()
            return True
        else:
            missing = expected_topics - actual_topics
            print(f"❌ Missing topics: {missing}")
            return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Kafka Topic Management for E-Commerce Analytics Pipeline"
    )
    parser.add_argument(
        "action",
        choices=["setup", "list", "describe", "consume"],
        help="Action to perform"
    )
    parser.add_argument(
        "--topic",
        help="Topic name (for describe/consume actions)"
    )
    parser.add_argument(
        "--num-messages",
        type=int,
        default=1,
        help="Number of messages to consume (default: 1)"
    )
    parser.add_argument(
        "--container",
        default="ecommerce-redpanda",
        help="Redpanda container name (default: ecommerce-redpanda)"
    )

    args = parser.parse_args()

    manager = KafkaTopicManager(args.container)

    if args.action == "setup":
        success = manager.setup_all_topics()
        sys.exit(0 if success else 1)

    elif args.action == "list":
        topics = manager.list_topics()
        print("Available topics:")
        for topic in topics:
            print(f"  - {topic}")

    elif args.action == "describe":
        if not args.topic:
            print("❌ --topic required for describe action")
            sys.exit(1)

        info = manager.describe_topic(args.topic)
        if info:
            print(f"Topic: {args.topic}")
            for key, value in info["config"].items():
                print(f"  {key}: {value}")

    elif args.action == "consume":
        if not args.topic:
            print("❌ --topic required for consume action")
            sys.exit(1)

        manager.consume_messages(args.topic, args.num_messages)


if __name__ == "__main__":
    main()