export const NotificationPlugin = async ({ project, $ }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.idle") {
        await $`osascript -e 'display notification "Task finished!" with title "opencode" subtitle "carhist-agent" sound name "Glass"'`
      }
      if (event.type === "session.error") {
        await $`osascript -e 'display notification "Session errored" with title "opencode" sound name "Basso"'`
      }
    },
  }
}