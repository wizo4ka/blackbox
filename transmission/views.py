from django.conf import settings
from django.http import HttpResponseBadRequest
from django.shortcuts import HttpResponse, render_to_response,\
    RequestContext, redirect
from django.views.decorators.csrf import csrf_exempt

import transmissionrpc
import tempfile
from base64 import b64encode
from json import dumps
from os import unlink, symlink
from hashlib import sha1
from random import random

from transmission.models import Torrent, Group, File, Hardlink


def api_add_torrent(request):
    if request.method == 'POST':
        tc = transmissionrpc.Client(
            settings.TRANSMISSION['default']['HOST'],
            port=settings.TRANSMISSION['default']['PORT'],
            user=settings.TRANSMISSION['default']['USER'],
            password=settings.TRANSMISSION['default']['PASSWORD'])

        if 'torrent' in request.FILES:
            with tempfile.NamedTemporaryFile('w+b', delete=False) as fp:
                f = request.FILES.get('torrent')
                tf = fp.name
                for chunk in f.chunks():
                    fp.write(chunk)

            fp.close()
            fp = open(tf, 'r')

            tc.add_torrent(b64encode(fp.read()))

            fp.close()
            unlink(tf)
        else:
            for url in request.POST['torrentUrls'].split("\n"):
                try:
                    tc.add_torrent(url)
                except:
                    pass

        return redirect('/')
    else:
        return HttpResponseBadRequest(
            content=dumps({
                'status': 'error',
                'reason': 'Request method should be POST'
            }), content_type='application/json'
        )


@csrf_exempt
def api_action(request, hash, action):
    tc = transmissionrpc.Client(
        settings.TRANSMISSION['default']['HOST'],
        port=settings.TRANSMISSION['default']['PORT'],
        user=settings.TRANSMISSION['default']['USER'],
        password=settings.TRANSMISSION['default']['PASSWORD'])

    torrent = tc.get_torrent(hash)
    torrent.name = Torrent.objects.get(hash=hash).name

    if action == 'delete':
        tc.remove_torrent(hash, delete_data=True)
    elif action == 'start':
        tc.start_torrent(hash)
    elif action == 'stop':
        tc.stop_torrent(hash)
    elif action == 'info':
        if request.method == 'GET':
            files = torrent.files()
            data = []
            for f in files:
                tobj = Torrent.objects.get(hash=hash)
                file, created = File.objects.get_or_create(
                    torrent=tobj,
                    filename=files[f]['name']
                )
                data.append('%s/%s' % (settings.SHARE_PATH, files[f]['name']))

            return HttpResponse(
                content=dumps({
                    'hash': hash,
                    'name': torrent.name,
                    'status': torrent.status,
                    'progress': torrent.progress,
                    'magnetLink': torrent.magnetLink,
                    'files': sorted(data)
                })
            )
        elif request.method == 'POST':
            t = Torrent.objects.get(hash=hash)
            t.name = request.POST.get('name', torrent.name)
            t.save()
            return HttpResponse(
                content=dumps({
                    'status': 'ok'
                }), content_type='application/json'
            )
        else:
            return HttpResponseBadRequest(
                content=dumps({
                    'status': 'error',
                    'reason': 'request type should be GET or POST'
                }), content_type='application/json'
            )
    elif action == 'verify':
        tc.verify_torrent(hash)
    else:
        return HttpResponseBadRequest(
            content=dumps({
                'status': 'error',
                'reason': 'No such method %s' % action
            }), content_type='application/json'
        )
    return HttpResponse(
        content=dumps({
            'status': 'ok'
        }), content_type='application/json'
    )


def api_list(request):
    tc = transmissionrpc.Client(
        settings.TRANSMISSION['default']['HOST'],
        port=settings.TRANSMISSION['default']['PORT'],
        user=settings.TRANSMISSION['default']['USER'],
        password=settings.TRANSMISSION['default']['PASSWORD'])

    filter = request.GET.get('filter', '')

    rpclist = tc.get_torrents()
    data = {}
    for t in rpclist:
        torrent, created = Torrent.objects.get_or_create(
            hash=t.hashString
        )
        if created:
            torrent.name = t.name
            torrent.save()

        data[t.hashString] = {
            'hash': t.hashString,
            'name': t.name,
            'status': t.status,
            'progress': t.progress,
            'recheckProgress': t.recheckProgress * 100,
        }

    for t in Torrent.objects.all():
        try:
            data[t.hash]['name'] = t.name
        except KeyError:
            t.delete()
            del(data[t.hash])

    return HttpResponse(
        content=dumps(data),
        content_type='application/json'
    )


def api_filter(request):
    tc = transmissionrpc.Client(
        settings.TRANSMISSION['default']['HOST'],
        port=settings.TRANSMISSION['default']['PORT'],
        user=settings.TRANSMISSION['default']['USER'],
        password=settings.TRANSMISSION['default']['PASSWORD'])

    filter = request.GET.get('query', '');
    data = {}
    for t in Torrent.objects.filter(name__icontains=filter):
        rpc = tc.get_torrent(t.hash)
        data[t.hash] = {
            'hash': t.hash,
            'name': t.name,
            'status': rpc.status,
            'progress': rpc.progress,
            'recheckProgress': rpc.recheckProgress * 100,
        }

    for f in File.objects.filter(filename__icontains=filter):
        rpc = tc.get_torrent(f.torrent.hash)
        data[f.torrent.hash] = {
            'hash': f.torrent.hash,
            'name': f.torrent.name,
            'status': rpc.status,
            'progress': rpc.progress,
            'recheckProgress': rpc.recheckProgress * 100,
        }


    return HttpResponse(
        content=dumps(data),
        content_type='application/json'
    )

def hardlink(request, file):
    file = File.objects.get(pk=file)

    token = sha1('%s:%s:%s' % (
        random(),
        file.pk,
        file.filename
    )).hexdigest()

    hardlink = Hardlink(
        token=token,
        file=file
    )
    hardlink.save()

    symlink(
        '%s/%s' % (
            settings.VAULT_PATH,
            file.filename
        ),
        '%s/%s' % (
            settings.HARDLINK_PATH,
            token
        )
    )

    return HttpResponse(
        content=dumps({
            'status': 'ok',
            'token': token
        }), content_type='application/json'
    )

def index(request):
    return render_to_response(
        'transmission/list.html',
        {'nav': 'transmission'},
        context_instance=RequestContext(request))
