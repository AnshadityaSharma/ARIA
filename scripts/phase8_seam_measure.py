"""Short native own-window experiment; not a Phase 8 endurance acceptance gate."""
from pathlib import Path
import argparse
import json
import platform
import statistics
import sys
import time
import tkinter as tk
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aria.seam_windows import enable_standalone_dpi
from aria.seam_ui import SeamWindow, seam_image
from aria.shard_presentation import DisplayState as S
from aria.seam_presentation import ActivityEvent, ActivityKind
from scripts.phase8_seam_demo import SyntheticSource


def summary(values):
    values = sorted(values)
    return {"n":len(values), "p50":statistics.median(values),
            "p95":values[min(len(values)-1, int((len(values)-1)*.95))], "max":max(values)} if values else {"n":0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=3.)
    args = parser.parse_args()
    if not .5 <= args.seconds <= 30:
        parser.error("--seconds must be between .5 and 30")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    enable_standalone_dpi()
    process = psutil.Process()
    rss_before_root = process.memory_info().rss
    root = tk.Tk()
    root.withdraw()
    rss_root = process.memory_info().rss
    cpu_at = process.cpu_times()
    baseline_at = time.perf_counter()
    root.after(round(args.seconds*1000), root.quit)
    root.mainloop()
    cpu_end = process.cpu_times()
    root_baseline_cpu = 100*((cpu_end.user+cpu_end.system)-(cpu_at.user+cpu_at.system))/(time.perf_counter()-baseline_at)
    start = time.perf_counter()
    ui = SeamWindow(root)
    source = SyntheticSource(ui.adapter)
    root.update()
    startup_ms = (time.perf_counter()-start)*1000
    foreground = ui.backend.api.GetForegroundWindow()
    def pump(seconds, signal=False):
        n = 0
        sample_job = None
        def sample():
            nonlocal n, sample_job
            import math
            ui.adapter.submit_activity(ActivityEvent(source.session, n, ActivityKind.INPUT, .5+.4*math.sin(n*.7)))
            n += 1
            sample_job = root.after(70, sample)
        if signal:
            sample()
        root.after(round(seconds*1000), root.quit)
        root.mainloop()
        if sample_job:
            root.after_cancel(sample_job)
    def stage(name, signal=False):
        before = process.cpu_times()
        at = time.perf_counter()
        paints = ui.paint_count
        pump(args.seconds, signal)
        after = process.cpu_times()
        wall = time.perf_counter()-at
        return {"stage":name, "wall_seconds":wall,
                "cpu_one_core_percent":100*((after.user+after.system)-(before.user+before.system))/wall,
                "rss_bytes":process.memory_info().rss, "paints":ui.paint_count-paints}
    try:
        pump(.5)
        idle = stage("visible_idle")
        ui.set_visible(False)
        hidden = stage("hidden_idle")
        ui.set_visible(True)
        for _ in range(30):
            source.start()
            pump(.03)
            source.send(S.FINAL, "Open Chrome", 0)
            source.send(S.EXECUTING)
            source.send(S.VERIFIED)
            pump(.035)
        source.start()
        pump(.2)
        active = stage("synthetic_voice_active", signal=True)
        pump(.4)
        source.show(S.UNVERIFIED)
        pump(.4)
        ui.expand(False)
        pump(.1)
        rss_before_capture = process.memory_info().rss
        # Export raster assets plus actual own-window crops, never full desktops.
        from PIL import ImageGrab
        shots=[]
        for name, window in (("compact", ui.compact), ("expanded", ui.panel)):
            box=(window.winfo_rootx(),window.winfo_rooty(),window.winfo_rootx()+window.winfo_width(),window.winfo_rooty()+window.winfo_height())
            shot=args.output.with_name("seam-native-"+name+".png")
            ImageGrab.grab(bbox=box, all_screens=True).save(shot)
            shots.append(str(shot))
        report={"platform":platform.platform(), "python":platform.python_version(),
                "logical_cores":psutil.cpu_count(), "physical_ram_bytes":psutil.virtual_memory().total,
                "work_area":ui.area.__dict__ if hasattr(ui.area,'__dict__') else {k:getattr(ui.area,k) for k in ['left','top','right','bottom','dpi']},
                "evidence":"Native Windows Tk + synthetic events only; short warm experiment, no live actions",
                "startup_to_tk_update_ms":startup_ms,"rss_before_root_bytes":rss_before_root,
                "root_only_idle_cpu_one_core_percent":root_baseline_cpu,
                "rss_before_screenshot_bytes":rss_before_capture,
                "rss_root_only_bytes":rss_root,"rss_final_bytes":process.memory_info().rss,
                "stages":[idle,hidden,active],
                "event_to_adapter_update_ms":summary(list(ui.adapter.latencies_ms)),
                "event_to_raster_and_tk_submit_ms":summary(list(ui.event_to_paint_ms)),
                "raster_and_tk_submit_ms":summary(list(ui.paint_ms)),
                "scheduled_animation_interval_ms":summary(list(ui.frame_intervals_ms)),
                "no_unrequested_foreground_change":ui.backend.api.GetForegroundWindow()==foreground,
                "screenshots":shots,"renderer_fault":ui.fault,
                "limitations":["No compositor/present timestamp", "Root-only baseline is not a non-UI ARIA process control", "Final RSS includes screenshot tooling; use before-screenshot and stage RSS", "One display and one scaling setting", "CPU counters are coarse at short durations", "No native screen-reader or endurance acceptance", "Foreground may change externally during experiment"]}
        start=time.perf_counter();ui.close();report['shutdown_ms']=(time.perf_counter()-start)*1000
        report['pending_jobs_after_close']=len(ui.jobs)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally:
        ui.close()
        root.destroy()


if __name__ == '__main__':
    main()
