from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods

from main.models import FileAttachment


def chat_view(request):
    return render(request, 'chat.html')


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
    return render(request, 'panel.html')


@login_required
@csrf_exempt
@require_http_methods(['POST'])
def upload(request):
    file = request.FILES['file']
    attachment = FileAttachment(file=file)
    attachment.save()

    # Get the channel layer
    channel_layer = get_channel_layer()

    # Create a new message for the WebSocket
    message = {
        'type': 'file_uploaded',
        'filename': attachment.file.name,
    }

    # Use async_to_sync to send the message on the channel layer
    async_to_sync(channel_layer.group_send)(request.POST['session_id'], message)

    return JsonResponse({'filename': attachment.file.name})
