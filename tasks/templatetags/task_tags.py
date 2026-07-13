from django import template

register = template.Library()


@register.filter
def is_task_assignee(task, user):
    return task.is_assigned_to(user)
