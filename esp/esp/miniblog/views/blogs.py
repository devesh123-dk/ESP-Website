from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404
from esp.web.util.main import render_to_response
from esp.miniblog.forms.form_comment import BlogCommentForm
from esp.miniblog.models import Entry, Comment
from esp.miniblog.decorators import miniblog_find


__all__ = ['single_blog_entry']


@miniblog_find
def single_blog_entry(request, entry, action):

    if 'success' in request.GET:
        return render_to_response('miniblog/comment_success.html',
                                  request, entry.anchor,
                                  {'entry':entry})

    if request.method == 'POST':
        form = BlogCommentForm(request.POST)

        if form.is_valid():
            c = Comment.objects.create(entry = entry,
                                       author = request.user,
                                       subject = form.clean_data['subject'],
                                       content = form.clean_data['content'])
            c.save()

            return HttpResponseRedirect(request.path +'?success')
    else:
        form = BlogCommentForm()


    return render_to_response('miniblog/single_blog.html',
                              request, entry.anchor,
                              {'entry': entry,
                               'form':  form})
