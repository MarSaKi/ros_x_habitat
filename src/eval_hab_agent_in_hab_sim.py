import argparse

import habitat
from habitat.config import Config
from habitat.config.default import get_config
from classes.habitat_discrete_evaluator import HabitatDiscreteEvaluator
from habitat_baselines.agents.ppo_agents import PPOAgent

# logging
from classes import utils_logging

logger = utils_logging.setup_logger(__name__)


def get_default_config():
    c = Config()
    c.INPUT_TYPE = "blind"
    c.MODEL_PATH = "data/checkpoints/blind.pth"
    c.RESOLUTION = 256
    c.HIDDEN_SIZE = 512
    c.RANDOM_SEED = 7
    c.PTH_GPU_ID = 0
    c.GOAL_SENSOR_UUID = "pointgoal_with_gps_compass"
    return c


def main():
    # parse input arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-type",
        default="blind",
        choices=["blind", "rgb", "depth", "rgbd"],
    )
    parser.add_argument("--model-path", default="", type=str)
    parser.add_argument(
        "--task-config", type=str, default="configs/pointnav_d_orignal.yaml"
    )
    parser.add_argument("--episode-id", type=str, default="-1")
    parser.add_argument(
        "--scene-id",
        type=str,
        default="data/scene_datasets/habitat-test-scenes/skokloster-castle.glb",
    )
    parser.add_argument("--log-dir", type=str, default="logs/")
    parser.add_argument("--video-dir", type=str, default="videos/")
    parser.add_argument("--tb-dir", type=str, default="tb/")
    args = parser.parse_args()

    # instantiate a discrete/continuous evaluator
    exp_config = get_config(args.task_config)
    evaluator = None
    if "SIMULATOR" in exp_config:
        logger.info("Instantiating discrete simulator")
        evaluator = HabitatDiscreteEvaluator(config_paths=args.task_config)
    elif "PHYSICS_SIMULATOR" in exp_config:
        logger.info("Instantiating continuous simulator with dynamics")
        raise NotImplementedError
    else:
        logger.info("Simulator not properly specified")
        raise NotImplementedError

    agent_config = get_default_config()
    agent_config.INPUT_TYPE = args.input_type
    agent_config.MODEL_PATH = args.model_path
    agent = PPOAgent(agent_config)

    logger.info("Started Evaluation")
    metrics = evaluator.evaluate(
        agent,
        episode_id_last=args.episode_id,
        scene_id_last=args.scene_id,
        log_dir=args.log_dir,
        video_dir=args.video_dir,
        tb_dir=args.tb_dir,
    )

    logger.info("Printing average metrics:")
    for k, v in metrics.items():
        logger.info("{}: {:.3f}".format(k, v))


if __name__ == "__main__":
    main()
