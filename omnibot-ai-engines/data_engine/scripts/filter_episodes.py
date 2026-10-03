"""filter_episodes.py
------------------
Filter demonstration episodes in a LeRobot v2.0 dataset based on quality rules:
  1. Identical frames for >0.5 s (frozen camera)
  2. Wrist vs bird's-eye view camera timestamp delta >50 ms (camera skew)
  3. Joint step >0.5 rad between consecutive frames (joint jump)
  4. Episode shorter than 2.0 s (short / abortive take)

Usage:
    python -m data_engine.scripts.filter_episodes \\
        --dataset /data/lerobot/pick_place \\
        --output /data/lerobot/pick_place/meta/filter_results.json
"""

from __future__ import annotations

from pathlib import Path
import sys

import click

from data_engine.quality.episode_filter import FilterThresholds, filter_dataset


@click.command()
@click.option(
    "--dataset",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="LeRobot dataset root directory",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output JSON path (default: <dataset>/meta/filter_results.json)",
)
@click.option(
    "--max-frozen-s",
    default=0.5,
    show_default=True,
    type=float,
    help="Max duration (s) of identical frames before rejection",
)
@click.option(
    "--max-camera-skew-s",
    default=None,
    type=float,
    help="Max timestamp delta (s) between wrist and BEV cameras (default: 0.05 s = 50 ms)",
)
@click.option(
    "--max-camera-skew-ms",
    default=None,
    type=float,
    help="Max timestamp delta in ms (alternative to --max-camera-skew-s, default: 50.0 ms)",
)
@click.option(
    "--max-joint-step-rad",
    default=0.5,
    show_default=True,
    type=float,
    help="Max joint step (rad) between consecutive frames before rejection",
)
@click.option(
    "--min-duration-s",
    default=2.0,
    show_default=True,
    type=float,
    help="Minimum episode duration (s) before rejection",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print detailed scoring for every episode",
)
def main(
    dataset: Path,
    output: Path | None,
    max_frozen_s: float,
    max_camera_skew_s: float | None,
    max_camera_skew_ms: float | None,
    max_joint_step_rad: float,
    min_duration_s: float,
    verbose: bool,
) -> None:
    """Score demonstration episodes and write a keep/reject JSON report."""
    # Resolve camera skew flag
    if max_camera_skew_s is not None:
        resolved_skew_s = max_camera_skew_s
    elif max_camera_skew_ms is not None:
        resolved_skew_s = max_camera_skew_ms / 1000.0
    else:
        resolved_skew_s = 0.05  # Default 50 ms

    # Resolve output path
    if output is None:
        meta_dir = dataset / "meta"
        out_path = meta_dir / "filter_results.json"
    else:
        out_path = output

    click.echo(f"Scoring dataset episodes: {dataset.resolve()}")
    click.echo(
        f"Thresholds: max_frozen={max_frozen_s:.2f}s, "
        f"max_camera_skew={resolved_skew_s * 1000.0:.1f}ms, "
        f"max_joint_step={max_joint_step_rad:.2f}rad, "
        f"min_duration={min_duration_s:.2f}s"
    )

    thresholds = FilterThresholds(
        max_frozen_s=max_frozen_s,
        max_camera_skew_s=resolved_skew_s,
        max_joint_step_rad=max_joint_step_rad,
        min_duration_s=min_duration_s,
    )

    result = filter_dataset(dataset, thresholds=thresholds, verbose=verbose)

    # Print results summary
    click.echo("\nEpisode Results:")
    for ep_idx, ep_score in result.episodes.items():
        if ep_score.passed:
            line = (
                f"  Episode {ep_idx:06d}: [KEEP]   "
                f"(duration={ep_score.metrics.duration_s:.2f}s, "
                f"joint_step={ep_score.metrics.max_joint_step_rad:.3f}rad, "
                f"skew={ep_score.metrics.max_camera_skew_s * 1000.0:.1f}ms, "
                f"frozen={ep_score.metrics.max_frozen_duration_s:.2f}s)"
            )
            if verbose or len(result.episodes) <= 20:
                click.echo(line)
        else:
            reasons_str = "; ".join(ep_score.reasons)
            click.echo(f"  Episode {ep_idx:06d}: [REJECT] {reasons_str}")

    click.echo("\n" + "=" * 50)
    click.echo("Filter Summary:")
    click.echo(f"  Total episodes:    {result.summary['total_episodes']}")
    click.echo(f"  Kept episodes:     {result.summary['kept_episodes']}")
    click.echo(f"  Rejected episodes: {result.summary['rejected_episodes']}")
    click.echo(f"  Keep ratio:        {result.summary['keep_ratio']:.1%}")
    click.echo("=" * 50)

    saved_path = result.save_json(out_path)
    click.echo(f"\nWrote keep/reject filter results to: {saved_path.resolve()}\n")


if __name__ == "__main__":
    main()
