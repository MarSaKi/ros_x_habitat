import argparse
import os

from typing import Dict
from collections import defaultdict

from habitat.config.default import get_config

from src.evaluators.habitat_ros_evaluator import HabitatROSEvaluator

from src.utils import utils_logging, utils_files


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
    parser.add_argument("--seed-file-path", type=str, default="seeds/seed=7.csv")
    parser.add_argument("--sensor-pub-rate", type=float, default=5.0)
    parser.add_argument(
        "--do-not-start-nodes-from-evaluator", default=False, action="store_true"
    )
    parser.add_argument("--log-dir", type=str, default="logs/")
    args = parser.parse_args()

    # get exp config
    exp_config = get_config(args.task_config)

    # get seeds if provided; otherwise use default seed from Habitat
    seeds = []
    if args.seed_file_path != "":
        seeds = utils_files.load_seeds_from_file(args.seed_file_path)
    else:
        seeds = [exp_config.SEED]

    # create log dir
    try:
        os.mkdirs(f"{args.log_dir}")
    except FileExistsError:
        pass

    # create logger and log experiment settings
    logger = utils_logging.setup_logger(
        __name__, f"{args.log_dir}/summary-all_seeds.log"
    )
    logger.info("Experiment configuration:")
    logger.info(exp_config)

    # instantiate a discrete/continuous evaluator
    evaluator = None
    if "PHYSICS_SIMULATOR" in exp_config:
        logger.info("Instantiating continuous simulator with dynamics")
        # TODO: pass in control period
        evaluator = HabitatROSEvaluator(
            config_paths=args.task_config,
            input_type=args.input_type,
            model_path=args.model_path,
            enable_physics=True,
            agent_node_name="agent_node",
            env_node_name="env_node",
            sensor_pub_rate=args.sensor_pub_rate,
            do_not_start_nodes=args.do_not_start_nodes_from_evaluator,
        )
    elif "SIMULATOR" in exp_config:
        logger.info("Instantiating discrete simulator")
        evaluator = HabitatROSEvaluator( 
            config_paths=args.task_config,
            input_type=args.input_type,
            model_path=args.model_path,
            enable_physics=False,
            agent_node_name="agent_node",
            env_node_name="env_node",
            sensor_pub_rate=args.sensor_pub_rate,
            do_not_start_nodes=args.do_not_start_nodes_from_evaluator,
        )
    else:
        logger.info("Simulator not properly specified")
        raise NotImplementedError

    logger.info("Started evaluation")
    avg_metrics_all_seeds = {}
    for seed in seeds:
        # create logger for each seed and log the seed
        logger_per_seed = utils_logging.setup_logger(
            f"{__name__}-seed={seed}", f"{args.log_dir}/summary-seed={seed}.log"
        )
        logger_per_seed.info(f"Seed = {seed}")

        # create (per-episode) log dir
        try:
            os.mkdirs(f"{args.log_dir}/seed={seed}")
        except FileExistsError:
            pass

        dict_of_metrics = evaluator.evaluate(
            episode_id_last=args.episode_id,
            scene_id_last=args.scene_id,
            log_dir=f"{args.log_dir}/seed={seed}",
            agent_seed=seed,
        )

        # compute average metrics of this seed
        avg_metrics_per_seed = evaluator.compute_avg_metrics(dict_of_metrics)

        # save to dict of avg metrics across all seeds
        avg_metrics_all_seeds[seed] = avg_metrics_per_seed

        # log average metrics of this seed
        logger_per_seed.info("Printing average metrics:")
        for k, v in avg_metrics_per_seed.items():
            logger_per_seed.info("{}: {:.3f}".format(k, v))
        utils_logging.close_logger(logger_per_seed)
    logger.info("Evaluation ended")

    # gracefully shutdown the env node and the agent node
    evaluator.shutdown_env_node()
    evaluator.shutdown_agent_node()

    # log average metrics across all seeds
    avg_metrics = evaluator.compute_avg_metrics(avg_metrics_all_seeds)
    logger.info("Printing average metrics:")
    for k, v in avg_metrics.items():
        logger.info("{}: {:.3f}".format(k, v))

    utils_logging.close_logger(logger)


if __name__ == "__main__":
    main()
