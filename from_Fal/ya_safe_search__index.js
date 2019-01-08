const https = require('https');
const querystring = require('querystring');
const util = require('util');
const zlib = require('zlib');
const { URL } = require('url');

const readline = require('readline').createInterface({
  input: process.stdin,
  output: process.stdout
});

let COOKIES = {};

const HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, sdch, br',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4',
    'Connection': 'close',
    'Host': 'yandex.ru',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    'X-Compress': 'null'
};

const yaRequest = async (url, headers = {}) => {
    const response = await new Promise(resolve => {
        https.request({
            method: 'GET',
            host: 'yandex.ru',
            path: url,
            headers: Object.assign({}, HEADERS, headers, { Cookie: COOKIES })
        }, res => {
            resolve(res);
        }).end();
    });
    
    if (response.statusCode === 302 && /showcaptcha/.test(response.headers['location'])) {
        await resolveCaptcha(response.headers['location']);

        return yaRequest(url, headers);
    }

    const c = (response.headers['set-cookie'] || [])
        .map(x => x.split(';', 1)[0]);
    Object.assign(COOKIES, parseCookies(c));

    return response;
}

function parseCookies(cookies) {
    return cookies.reduce((m, c) => {
        const parts = c.split('=');
        m[parts[0]] = parts[1];
        return m;
    }, {});
}

async function refreshCookies() {
    COOKIES = {};

    const init = await yaRequest('/images/search?text=ssd');
    const yandexUid = COOKIES['yandexuid'];

    const retpath = 'https%3A%2F%2Fyandex.ru%2Fimages%2Fsearch%3Ftext%3Dssd';
    const family = await yaRequest(`/images/customize?save=1&retpath=${retpath}&yandexuid=${yandexUid}&family=2`,
        { Referer: 'https://yandex.ru/images/search?text=ssd' });
}

async function readBody(response) {
    let stream = response;
    if(response.headers['content-encoding'] == 'gzip') {
        const gzip = zlib.createGunzip();
        response.pipe(gzip);
        stream = gzip;
    }

    return new Promise((resolve, reject) => {
        let data = '';

        stream.on('end', () => resolve(data));
        stream.on('error', err => { debugger; reject(err) });
        stream.on('data', chunk => data += chunk.toString('utf-8'));
    });
}


async function resolveCaptcha(url) {
    url = new URL(url);
    const response = await yaRequest(url.pathname + url.search);
    const body = await readBody(response);
    if (response.statusCode !== 200) {
        throw new Error('failed to resolve captcha');
    }

    const m = body.match(/src="(https?:\/\/yandex.ru\/captchaimg[^"]+)/);
    const captchaUrl = m[1];

    let answer = '';
    debugger;

    const getValue = tagStr => tagStr.split(' ').find(x => /^value/.test(x)).replace(/^.*="|">?$/, '');   

    const postData = querystring.stringify({
        rep: answer,
        key: getValue(body.match(/<input[^>]*name="key"[^>]*>/)[0]),
        retpath: getValue(body.match(/<input[^>]*name="retpath"[^>]*>/)[0])
    });

    let resolveResponsePromise;
    let postResponsePromise = new Promise(resolve => resolveResponsePromise = resolve);

    const postRequest = https.request({
        host: 'yandex.ru',
        path: '/checkcaptcha',
        method: 'POST',
        headers: Object.assign({}, HEADERS, {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Content-Length': Buffer.byteLength(postData)
        })
    }, resolveResponsePromise);

    postRequest.write(postData);
    postRequest.end();

    const postResponse = await postResponsePromise;

    const c = (postResponse.headers['set-cookie'] || [])
        .map(x => x.split(';', 1)[0]);
    Object.assign(COOKIES, parseCookies(c));
}

refreshCookies()
    .then(cookies => console.log(cookies))
    .catch(err => console.error(err))
    .then(() => {
        console.dir(COOKIES);
        readline.close();
    });

async function search(request) {
    const response = await yaRequest('/images/search?text=' + encodeURIComponent(request));
    if (response.statusCode !== 200) {
        throw new Error(`search failed, dunno what happened. Status code: ${response.statusCode}`);
    }

    const html = await readBody(response);

    debugger;
}
