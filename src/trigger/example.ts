import { logger, schedules } from "@trigger.dev/sdk/v3";
import { runTask } from "../main";

export const checkOptionsTask = schedules.task({
  id: "check-options-task",
  // Every hour
  cron: "0 * * * *",
  // Set an optional maxDuration to prevent tasks from running indefinitely
  maxDuration: 300, // Stop executing after 300 secs (5 mins) of compute
  run: async () => {
    logger.info("running task");
    const start = Date.now();
    await runTask();
    logger.info("Task finished successfully");
  },
});
