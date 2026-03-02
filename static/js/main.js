function likePost(postId) {
  fetch('/post/' + postId + '/like', { method: 'POST' })
    .then(function(r) { return r.json() })
    .then(function(data) {
      var btn = document.getElementById('like-btn-' + postId)
      if (btn) btn.textContent = data.status === 'liked' ? '❤️' : '🤍'
      var count = document.getElementById('likes-' + postId)
      if (count) count.textContent = data.count + ' likes'
      if (data.status === 'liked') {
        var heart = document.getElementById('heart-' + postId)
        if (heart) {
          heart.style.opacity = '1'
          heart.style.transform = 'scale(1.4)'
          setTimeout(function() {
            heart.style.opacity = '0'
            heart.style.transform = 'scale(1)'
          }, 700)
        }
      }
    })
    .catch(function(e) { console.log('like error', e) })
}

function toggleComments(postId) {
  var section = document.getElementById('comments-' + postId)
  if (section) {
    section.style.display =
      (section.style.display === 'none' || section.style.display === '')
        ? 'block' : 'none'
  }
}

function submitComment(postId) {
  var input = document.getElementById('comment-input-' + postId)
  if (!input) return
  var text = input.value.trim()
  if (!text) return
  var fd = new FormData()
  fd.append('text', text)
  fetch('/post/' + postId + '/comment', { method: 'POST', body: fd })
    .then(function(r) { return r.json() })
    .then(function(data) {
      if (data.error) return
      var section = document.getElementById('comments-' + postId)
      if (section) {
        section.style.display = 'block'
        var p = document.createElement('p')
        p.className = 'comment-line'
        p.innerHTML = '<span class="username">' + data.username + '</span> ' + data.text
        section.appendChild(p)
      }
      input.value = ''
    })
    .catch(function(e) { console.log('comment error', e) })
}

function savePost(postId, btn) {
  fetch('/post/' + postId + '/save', { method: 'POST' })
    .then(function(r) { return r.json() })
    .then(function(data) {
      if (btn) btn.textContent = data.status === 'saved' ? '🔖' : '🏷️'
    })
    .catch(function(e) { console.log('save error', e) })
}

function viewStory(storyId) {
  fetch('/story/' + storyId + '/view', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ screenshot: false })
  }).catch(function(e) { console.log('story error', e) })
  var overlay = document.createElement('div')
  overlay.id = 'story-overlay'
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;'
  overlay.innerHTML =
    '<div style="text-align:center;padding:20px">' +
    '<button onclick="document.getElementById(\'story-overlay\').remove()" ' +
    'style="display:block;margin:0 auto 20px;background:none;border:none;color:#fff;font-size:32px;cursor:pointer">✕</button>' +
    '<p style="color:#fff;font-size:16px;font-weight:700">📖 Story viewed!</p>' +
    '</div>'
  document.body.appendChild(overlay)
  setTimeout(function() {
    var o = document.getElementById('story-overlay')
    if (o) o.remove()
  }, 5000)
}

function toggleFollow(userId, btn) {
  fetch('/user/' + userId + '/follow', { method: 'POST' })
    .then(function(r) { return r.json() })
    .then(function(data) {
      if (data.status === 'followed') {
        btn.textContent = 'Following ✓'
        btn.style.background = '#f3f4f6'
        btn.style.color = '#111'
      } else {
        btn.textContent = 'Follow'
        btn.style.background = 'linear-gradient(135deg,#a855f7,#ec4899)'
        btn.style.color = '#fff'
      }
    })
    .catch(function(e) { console.log('follow error', e) })
}

function pollNotifications() {
  fetch('/notifications/count')
    .then(function(r) { return r.json() })
    .then(function(data) {
      var badge = document.getElementById('notif-badge')
      if (badge) {
        if (data.count > 0) {
          badge.textContent = data.count
          badge.style.display = 'flex'
        } else {
          badge.style.display = 'none'
        }
      }
    })
    .catch(function() {})
}

document.addEventListener('DOMContentLoaded', function() {
  pollNotifications()
  setInterval(pollNotifications, 30000)
})