from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods

from main.models import ChatMessage, ChatSession


def chat_view(request):
    return render(request, 'chat.html', context={'HOSTNAME': settings.HOSTNAME, 'IS_HTTPS': settings.IS_HTTPS})


@ensure_csrf_cookie
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('panel')
            else:
                form.add_error(None, "Invalid username or password")
    else:
        form = AuthenticationForm()
    return render(request, "login.html", {"form": form})


@login_required
def panel_view(request):
    return render(request, 'panel.html', context={'HOSTNAME': settings.HOSTNAME, 'IS_HTTPS': settings.IS_HTTPS})


@login_required
@csrf_exempt
@require_http_methods(['POST'])
def upload(request):
    session = ChatSession.objects.get(pk=request.POST['session_id'])
    message = request.POST['message']

    chat_message = ChatMessage(session=session, file=request.FILES['file'], message=None, response=message)
    chat_message.save()

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(session.sid, {
        'type': 'file_uploaded',
        'command': 'file_uploaded',
        'message': message,
        'file': chat_message.file.name,
    })
    async_to_sync(channel_layer.group_send)('panel', {
        'type': 'file_uploaded',
        'command': 'file_uploaded',
        'session_id': session.pk,
        'message': {
            'id': chat_message.id,
            'response': message,
            'file': chat_message.file.name,
        }
    })

    return JsonResponse({'filename': chat_message.filename})
