'use strict';

(() => {
  const meetingDate = '2026-11-10';
  const endDate = '2026-11-30';
  const storageKey = 'jingsen:father-son-meeting:2026-11-10:v1';
  const answerFields = [
    ['child_quote', '靖森的回答', '写下他的回答，尽量保留原话']
  ];
  const planFields = [
    ['action', '靖森的计划', '写下他打算做什么、什么时候做，以及怎么检查或求助']
  ];
  const stages = [
    {
      id: 'intention', title: '听他的想法', time: '约5分钟',
      confirmation: '听他用自己的话说出现在的想法、理由和最难的地方。给他时间想，也可以留待下次再谈。',
      guide: ['开场可以这样说', '我记得你说想继续兼顾学习和棒球。今天我想先听听你怎么想，再一起看看接下来三周可以怎么安排。'],
      items: [
        ['current', '你现在还想继续兼顾学习和棒球吗？', '允许他补充或改变想法，先把话听完。', true],
        ['reasons', '你想继续留在现在的学校、继续打棒球，各是因为什么？', '可以分别举一个最近发生的例子。', true],
        ['year', '如果由你来安排，未来一年你想过怎样的生活？', '可以聊上学、训练、朋友和休息。'],
        ['challenge', '你觉得兼顾最难的地方是什么？', '请他想一个上学和训练撞在一起的日子。', true]
      ]
    },
    {
      id: 'now', title: '弄清目前的困难', time: '约10分钟',
      confirmation: '请靖森说说卡在知识、时间、提醒还是帮助上，再用近期的作业或训练举个例子。',
      items: [
        ['subjects', '哪两门课现在最费劲？具体卡在哪里？', '可以回想一道题、一份作业，或一个没听懂的概念。', true],
        ['study', '你什么时候学得最进去？哪些事容易拖延或要人提醒？', '追问遇到不会的内容时，通常怎么做、可以找谁帮忙。'],
        ['baseball', '棒球上，你觉得自己最擅长什么？最想补哪一项？', '请举一次训练或比赛的例子。可以多记一两个强项和弱项。', true],
        ['practice', '除了球队训练，你最近主动练过什么？', '聊聊练了什么、怎么知道有进步、希望教练给什么反馈。']
      ]
    },
    {
      id: 'options', title: '聊聊取舍与求助', time: '约5分钟',
      confirmation: '听他怎么理解时间冲突和训练负荷，以及他希望得到什么帮助。',
      guide: ['需要时再谈其他安排', '继续在现在的学校读书并打球，可谈学习、训练和休息怎么排。考虑异地训练，可先向校方与教练核实训练强度、生活和文化课安排。考虑换学校或调整训练投入，可先核实转学与训练资源。今天可以只记录疑问。'],
      items: [
        ['tradeoffs', '作业、训练和休息撞在一起时，你想怎样安排？', '用下周真实的一天试排。有哪些地方需要父母或教练配合？'],
        ['help', '如果认真试过一段时间，还是很难兼顾，你希望我们怎么帮你？', '先听他希望得到哪一种帮助，再商量谁去联系或调整。', true]
      ]
    },
    {
      id: 'plan', title: '定下21天计划', time: '约10分钟',
      confirmation: '让靖森先提出做法。把行动、时间、检查方式和支持写清，复盘时可直接修订。',
      items: [
        ['learning-start', '学习主动性', '在哪个时段自己开始？训练日要怎么调？'],
        ['learning-quality', '学习质量与求助', '先补哪个具体难点？怎样订正或确认自己理解了？'],
        ['baseball-focus', '棒球训练与弱项', '和教练确认一个练习重点，写下能观察到的变化。'],
        ['routine', '作息与中断后的调整', '留出休息时间。某天打乱之后，下一次怎么重新开始？']
      ],
      fields: planFields
    },
    {
      id: 'roles', title: '确认双方责任', time: '约5分钟',
      confirmation: '请靖森复述自己的安排。父母也明确自己能做到的支持，允许有分歧或暂时留空。',
      guide: ['结束时可以这样说', '我听到了你想兼顾的理由。接下来我们照刚才说好的试一试，遇到卡住的时候一起调整。30日我们再看看这段时间发生了什么。'],
      items: [
        ['child-role', '从明天开始，你愿意先做哪几件和以前不同的事？', '请他说说自己如何开始、怎么反馈、做不到时怎样求助。', true],
        ['parent-role', '父母具体怎么帮？哪些提醒你能接受？', '商量学习帮助、训练协调和提醒频率。写清谁负责。', true],
        ['pending', '还有什么没有谈拢，或者需要找老师、教练核实？', '可以写待确认的事、负责人和回来讨论的时间。']
      ]
    },
    {
      id: 'review-15', title: '11月15日短复盘', date: '2026-11-15',
      confirmation: '看计划有没有顺利启动。挑一处卡点，约好下一周要做的一项小调整。',
      items: [['review', '过去几天哪些事开始做了？哪里卡住了？', '请靖森举一次主动开始和一次遇阻的例子，说说哪些帮助有用。']]
    },
    {
      id: 'review-22', title: '11月22日短复盘', date: '2026-11-22',
      confirmation: '看前一次调整是否有效，并找出被打断后能重新开始的做法。',
      items: [['review', '这周什么做法还能继续？哪些需要调整？', '对照学习启动和订正、训练弱项、休息和父母支持。记录变化及发生的情境。']]
    },
    {
      id: 'review-30', title: '11月30日正式复盘', date: endDate,
      confirmation: '回看21天的过程、变化与实际负荷，听完靖森的意见再商定下一阶段。',
      items: [
        ['process', '21天里，哪些变化有具体例子？哪些还需要时间？', '结合学习主动性、学习质量、棒球主动性、持续性和中断后的恢复。'],
        ['direction', '接下来哪些安排想继续、调整或再观察？', '请靖森说说他的理由、还想了解什么、希望什么时候再聊。']
      ]
    }
  ];

  const stagePanel = document.querySelector('#stage');
  const stageNav = document.querySelector('#stages');
  const saveState = document.querySelector('#save-state');
  const saveButton = document.querySelector('#save-draft');
  const dirty = {};
  let step = 0;
  let draft = {};

  function readDraft() {
    const raw = localStorage.getItem(storageKey);
    const stored = raw ? JSON.parse(raw) : {};
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) {
      throw new Error('Invalid meeting draft');
    }
    return stored;
  }

  function saveMessage(message, warning = false) {
    saveState.textContent = message;
    saveState.toggleAttribute('data-warning', warning);
  }

  function initStorage() {
    try {
      draft = readDraft();
      localStorage.setItem(storageKey, JSON.stringify(draft));
      saveMessage(Object.keys(draft).length ? '已恢复本机草稿' : '本机自动保存');
    } catch {
      saveMessage('本机保存不可用，请及时导出', true);
    }
  }

  function saveDraft(confirmed = false) {
    try {
      const merged = { ...readDraft(), ...dirty };
      localStorage.setItem(storageKey, JSON.stringify(merged));
      draft = merged;
      Object.keys(dirty).forEach(key => delete dirty[key]);
      saveMessage(confirmed ? '保存成功 · 仅此浏览器' : '已自动保存');
    } catch {
      saveMessage('本机保存失败，请及时导出', true);
    }
  }

  const fieldKey = (stage, item, field) => [stage.id, item[0], field].join('.');
  const valueFor = key => typeof draft[key] === 'string' ? draft[key] : '';
  const fieldsFor = stage => stage.fields || answerFields;

  function updateCount() {
    const keyItems = stages.flatMap(stage => stage.items.filter(item => item[3]).map(item => [stage, item]));
    const recorded = keyItems.filter(([stage, item]) => valueFor(fieldKey(stage, item, 'child_quote')).trim()).length;
    document.querySelector('#recorded').textContent = '重点已记录 ' + recorded + ' / ' + keyItems.length;
  }

  function render(focus = false) {
    const stage = stages[step];
    stageNav.innerHTML = stages.map(({ title }, index) =>
      '<button type="button" class="step-button" data-stage="' + index + '"' +
      (index === step ? ' aria-current="step"' : '') + '><span class="stage-number">' +
      String(index + 1).padStart(2, '0') + '</span>' + title + '</button>'
    ).join('');
    const guide = stage.guide
      ? '<details class="guide-note"><summary>' + stage.guide[0] + '</summary><p>' + stage.guide[1] + '</p></details>'
      : '';
    stagePanel.innerHTML = '<header class="section-head"><h2 id="stage-title" tabindex="-1">' + stage.title +
      '</h2><span class="phase-time">' + (stage.time || (stage.date === endDate ? '正式复盘' : '短复盘')) +
      '</span><p class="confirmation"><strong>重点确认</strong> · ' + stage.confirmation + '</p></header>' + guide +
      stage.items.map((item, index) => renderItem(stage, item, index)).join('') +
      '<div class="stage-actions"><button type="button" class="button secondary" data-stage="' + (step - 1) + '"' +
      (step === 0 ? ' disabled' : '') + '>上一阶段</button>' +
      (step < stages.length - 1
        ? '<button type="button" class="button" data-stage="' + (step + 1) + '">下一阶段</button>'
        : '<a class="button" href="#export-title">前往导出</a>') + '</div>';
    stagePanel.querySelectorAll('textarea').forEach(input => {
      input.value = valueFor(input.id);
    });
    updateCount();
    if (focus) {
      const heading = document.querySelector('#stage-title');
      heading.focus({ preventScroll: true });
      heading.scrollIntoView({ block: 'start' });
    }
  }

  function renderItem(stage, item, index) {
    const titleId = stage.id + '-question-' + index;
    const fields = fieldsFor(stage).map(([key, label, placeholder]) => {
      const id = fieldKey(stage, item, key);
      return '<div><label for="' + id + '">' + label + '</label><textarea id="' + id +
        '" maxlength="12000" aria-describedby="' + titleId + '" placeholder="' + placeholder + '"></textarea></div>';
    }).join('');
    return '<section class="record-group" aria-labelledby="' + titleId + '">' +
      (item[3] ? '<p class="key-label">重点问题</p>' : '') + '<h3 id="' + titleId + '">' +
      (index + 1) + ' · ' + item[1] + '</h3><p class="hint">' + item[2] +
      '</p><div class="record-fields">' + fields + '</div></section>';
  }

  function exportData() {
    return {
      schema_version: 1,
      meeting: { participant: '靖森', topic: '学习与棒球 · 父子谈话', date: meetingDate },
      action_period: { start: meetingDate, end: endDate, days: 21 },
      exported_at: new Date().toISOString(),
      stages: stages.map(stage => ({
        id: stage.id,
        title: stage.title,
        date: stage.date || meetingDate,
        suggested_duration: stage.time || null,
        confirmation: stage.confirmation,
        guide: stage.guide ? { label: stage.guide[0], text: stage.guide[1] } : null,
        items: stage.items.map(item => ({
          id: item[0],
          prompt: item[1],
          follow_up: item[2],
          key_question: Boolean(item[3]),
          records: Object.fromEntries(fieldsFor(stage).map(([key]) => [key, valueFor(fieldKey(stage, item, key))]))
        }))
      }))
    };
  }

  function toMarkdown(data) {
    const lines = ['# 靖森｜学习与棒球 · 父子谈话', '', '- 谈话日期：' + data.meeting.date,
      '- 行动期：' + data.action_period.start + ' 至 ' + data.action_period.end + '（共21天）',
      '- 导出时间（UTC）：' + data.exported_at,
      '', '记录说明：「未填写」表示该栏为空。谈话和复盘记录靖森的回答，行动计划单独列出。'];
    data.stages.forEach((stage, index) => {
      lines.push('', '## ' + (index + 1) + '. ' + stage.title, '', '- 日期：' + stage.date);
      if (stage.suggested_duration) lines.push('- 建议用时：' + stage.suggested_duration);
      lines.push('- 重点确认：' + stage.confirmation);
      if (stage.guide) lines.push('- ' + stage.guide.label + '：' + stage.guide.text);
      stage.items.forEach((item, itemIndex) => {
        lines.push('', '### ' + (itemIndex + 1) + '. ' + item.prompt, '');
        if (item.key_question) lines.push('- 重点问题');
        lines.push('- 追问提示：' + item.follow_up);
        fieldsFor(stages[index]).forEach(([key, label]) => {
          const note = item.records[key];
          lines.push('', '**' + label + '**', '',
            ...(note.trim() ? note.replace(/\r\n?/g, '\n').split('\n').map(line => '> ' + line.replace(/[&<>]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[char])) : ['未填写']));
        });
      });
    });
    return lines.join('\n') + '\n';
  }

  function download(format) {
    const data = exportData();
    const contents = format === 'json' ? JSON.stringify(data, null, 2) + '\n' : toMarkdown(data);
    const url = URL.createObjectURL(new Blob([contents], { type: format === 'json' ? 'application/json' : 'text/markdown;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = '父子谈话记录-' + meetingDate + '.' + format;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    document.querySelector('#export-feedback').textContent = '已发起下载，请查看浏览器的下载列表。';
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.dataset.stage !== undefined) {
      step = Number(button.dataset.stage);
      render(true);
    }
    if (button.dataset.export) download(button.dataset.export);
  });

  stagePanel.addEventListener('input', event => {
    if (event.target.tagName !== 'TEXTAREA') return;
    const { id, value } = event.target;
    draft[id] = value;
    dirty[id] = value;
    saveDraft();
    updateCount();
  });

  window.addEventListener('storage', event => {
    if (event.key !== storageKey && event.key !== null) return;
    try {
      draft = { ...readDraft(), ...dirty };
      stagePanel.querySelectorAll('textarea').forEach(input => {
        if (input !== document.activeElement) input.value = valueFor(input.id);
      });
      updateCount();
    } catch {
      saveMessage('草稿读取失败，请及时导出', true);
    }
  });

  saveButton.addEventListener('click', () => saveDraft(true));
  initStorage();
  render();
  saveButton.disabled = false;
  document.querySelectorAll('[data-export]').forEach(button => { button.disabled = false; });
})();
