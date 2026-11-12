const url = 'ws://' + location.hostname + ':9090';
const ros = new ROSLIB.Ros({ url: url });
ros.connect(url);
window.ros = ros;
window.rosbridgeUrl = url;
const params = Object.fromEntries(new URLSearchParams(window.location.search).entries());

ros.on('connection', function () {
	document.body.classList.add('connected');
	document.body.classList.remove('closed');
	init();
});

ros.on('error', function (e) { console.error('rosbridge error', e); document.body.classList.add('closed'); });

ros.on('close', function () {
	document.body.classList.remove('connected');
	document.body.classList.add('closed');
	setTimeout(function() {
		// reconnect
		ros.connect(url);
	}, 2000);
});

const title = document.querySelector('h1');
const topicsList = document.querySelector('#topics');
const topicMessage = document.querySelector('#topic-message');

function viewTopicsList() {
        console.log("viewTopicsList called");
        title.innerHTML = 'Topics:';

        // Используем ROSLIB.Service для прямого вызова сервиса
        const topicsService = new ROSLIB.Service({
                ros: ros,
                name: '/rosapi/topics',
                serviceType: 'rosapi/Topics'
        });

        const request = new ROSLIB.ServiceRequest({});

        topicsService.callService(request, function(result) {
                console.log("Service response:", result);
                if (result && result.topics && result.types) {
                        topicsList.innerHTML = result.topics.map(function(topic, i) {
                                const type = result.types[i] || 'unknown';
                                if (type == 'sensor_msgs/Image') {
                                        let url = `${location.protocol}//${location.hostname}:8080/stream_viewer?topic=${topic}`;
                                        return `<li><a href="${url}" class=topic title=${type}>${topic}</a> &#x1F5BC;</li>`;
                                } else {
                                        return `<li><a href="?topic=${topic}" class=topic title=${type}>${topic}</a></li>`;
                                }
                        }).join('');
                } else {
                        console.error("Invalid service response:", result);
                        topicsList.innerHTML = '<li>Error: Invalid response from service</li>';
                }
        }, function(error) {
                console.error("Service call error:", error);
                topicsList.innerHTML = '<li>Error: ' + error + '</li>';
        });
}

let rosdistro;

function viewTopic(topic) {
	let counter = 0;
	let index = '<a href=topics.html>Topics</a>';
	title.innerHTML = `${index}: ${topic}`;
	topicMessage.style.display = 'block';

	ros.getTopicType(topic, function(typeStr) {
		const [pack, type] = typeStr.split('/');
		let href = `https://docs.ros.org/en/${rosdistro}/api/${pack}/html/msg/${type}.html`;
		title.innerHTML = `${index}: ${topic} <a id="topic-type" href=${href} target="_blank">${typeStr}</a>`;
	});

	new ROSLIB.Topic({ ros: ros, name: topic }).subscribe(function(msg) {
		counter++;
		document.title = topic;
		if (mouseDown) return;

		if (msg.header && msg.header.stamp) {
			if (params.date || params.offset) {
				let date = new Date(msg.header.stamp.secs * 1e3 + msg.header.stamp.nsecs * 1e-6);
				if (params.date) msg.header.date = date.toISOString();
				if (params.offset) msg.header.offset = (new Date() - date) * 1e-3;
			}
		}

		let txt = `<div class=counter>${counter} received</div>${yamlStringify(msg)}`; // JSON.stringify(msg, null, 4);
		topicMessage.innerHTML = txt;
	});
}

let mouseDown;

topicMessage.addEventListener('mousedown', function() { mouseDown = true; });
topicMessage.addEventListener('mouseup', function() { mouseDown = false; });

function init() {
        console.log("init() called, params:", params);
	if (!params.topic) {
		viewTopicsList();
	} else {
		new ROSLIB.Param({ ros: ros, name: '/rosdistro'}).get(function(value) {
			rosdistro = value.trim();
			viewTopic(params.topic);
		});
	}
}
