from apps.automations.models import Automation, Run
from apps.sessions.models import Session
from apps.tasks.models import Task


AutomationStateChoices = Automation.State.choices
RunStatusChoices = Run.Status.choices
RunStartStatusChoices = [(Run.Status.RUNNING, "実行中")]
RunFinishStatusChoices = [
    (Run.Status.SUCCEEDED, "成功"),
    (Run.Status.FAILED, "失敗"),
]
TaskStatusChoices = Task.Status.choices
TaskPriorityChoices = Task.Priority.choices
TaskActorChoices = Task.Actor.choices
SessionAgentChoices = Session.Agent.choices
