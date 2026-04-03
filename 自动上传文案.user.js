// ==UserScript==
// @name         网站自动上传文案 2.1.0
// @namespace    http://tampermonkey.net/
// @version      2.1.0
// @description  创建一个按钮来自动上传文案，并实时更新进度条
// @author       name
// @match        https://showzstore.com/manage/?m=products&a=products&d=edit
// @match        https://www.gundamit.com/manage/?m=products&a=products&d=edit
// @match        https://gkloot.com/manage/?m=products&a=products&d=edit
// @grant        none
// @require      https://cdn.jsdelivr.net/npm/papaparse@5.3.2/papaparse.min.js
// ==/UserScript==

(function () {
    'use strict';

    // ================= UI 创建 =================

    const uploadSpan = document.createElement("div");
    uploadSpan.className = 'input';
    uploadSpan.style.display = 'flex';
    uploadSpan.style.alignItems = 'center';
    uploadSpan.style.marginTop = '10px';

    const uploadButton = document.createElement('input');
    uploadButton.type = 'button';
    uploadButton.className = 'btn_ok';
    uploadButton.value = '自动上传文案';
    uploadButton.style.display = 'block';
    uploadButton.style.backgroundColor = 'green';
    uploadButton.style.color = 'white';
    uploadSpan.appendChild(uploadButton);

    const progressContainer = document.createElement('div');
    progressContainer.style.zIndex = '9999';
    progressContainer.style.width = '300px';
    progressContainer.style.padding = '10px';
    progressContainer.style.display = 'none';
    uploadSpan.appendChild(progressContainer);

    const targetElement = document.querySelector('#header');
    if (targetElement) {
        targetElement.parentNode.insertBefore(uploadSpan, targetElement.nextSibling);
    } else {
        document.body.insertBefore(uploadSpan, document.body.firstChild);
    }

    uploadButton.addEventListener('click', startScript);

    function createProgressBar() {
        const progressBar = document.createElement('div');
        progressBar.style.width = '0';
        progressBar.style.height = '20px';
        progressBar.style.backgroundColor = '#2196f3';
        progressBar.style.textAlign = 'center';
        progressBar.style.lineHeight = '20px';
        progressBar.style.color = 'white';
        progressBar.style.marginLeft = '10px';
        progressBar.style.marginBottom = '5px';
        progressBar.innerText = '0%';
        progressContainer.innerHTML = '';
        progressContainer.appendChild(progressBar);
        return progressBar;
    }

    function updateProgressBar(progressBar, percent) {
        const normalizedPercent = Math.min(Math.max(percent, 0), 100);
        progressBar.style.width = normalizedPercent + '%';
        progressBar.innerText = normalizedPercent + '%';
    }

    // ================= 主流程 =================

    async function startScript() {
        progressContainer.style.display = 'block';
        const progressBar = createProgressBar();
        try {
            await runScript(progressBar);
            updateProgressBar(progressBar, 100);
            progressBar.style.backgroundColor = '#4caf50';
            progressBar.innerText = '完成';
        } catch (error) {
            updateProgressBar(progressBar, 100);
            progressBar.style.backgroundColor = '#f44336';
            progressBar.innerText = '失败: ' + error.message;
            console.error(error);
        }
    }

    async function runScript(progressBar) {
        updateProgressBar(progressBar, 5);
        const data = await fetchDataFromSheet();
        updateProgressBar(progressBar, 20);
        await fillInFields(data, progressBar);
        updateProgressBar(progressBar, 95);
        updateProgressBar(progressBar, 100);
    }

    // ================= 数据获取 =================

    async function fetchDataFromSheet() {
        const spreadsheetId = '1tzFJ83HjXcDLnJDBenlI5DvnjYQDxetIvY_0IqNPjZ0';
        const gid = '0';
        const csvUrl = `https://docs.google.com/spreadsheets/d/${spreadsheetId}/export?format=csv&gid=${gid}`;
        const csvResponse = await fetch(csvUrl);
        if (!csvResponse.ok) {
            throw new Error('无法获取 Google Sheets 数据');
        }
        const csvText = await csvResponse.text();

        const csvData = Papa.parse(csvText, {
            header: false,
            skipEmptyLines: true
        }).data;

        const data = {};
        const cellIndexMappings = {
            '1,1': 'product_title',
            '2,1': 'category',
            '3,1': 'number',
            '4,1': 'search_keyword',
            '5,1': 'page_url',
            '6,1': 'description_en',
            '11,1': 'seo_keyword_en',
            '12,1': 'seo_description_en',
            '14,1': 'price',
            '17,1': 'stock',
            '18,1': 'is_coming',
            '19,1': 'presale_price',
            '20,1': 'pre_discount',
            '21,1': 'length',
            '22,1': 'width',
            '23,1': 'height',
            '24,1': 'weight',
            '29,1': 'is_batteries'
        };

        for (const key in cellIndexMappings) {
            const [rowIndex, colIndex] = key.split(',').map(Number);
            const fieldName = cellIndexMappings[key];
            if (csvData[rowIndex] && csvData[rowIndex][colIndex] !== undefined) {
                data[fieldName] = csvData[rowIndex][colIndex];
            } else {
                data[fieldName] = '';
            }
        }

        console.log('解析后的数据：', data);
        return data;
    }

    // ================= API 配置 =================

    const API_CONFIG = {
        baseUrl: 'https://api.deepseek.com/chat/completions',
        apiKey: 'sk-240445142ba34cfcb03c55c6938ef67b',
        model: 'deepseek-chat'
    };

    // ================= 通用 AI 属性匹配工具 =================

    function extractOptionsFromDOM(container) {
        const buttons = container.querySelectorAll('.choice_btn');
        return Array.from(buttons).map(btn => btn.textContent.trim().split('\n')[0].trim());
    }

    function selectOptionInDOM(container, targetText, defaultText) {
        const options = container.querySelectorAll('.choice_btn');

        // 先取消所有已选中的选项
        options.forEach(opt => {
            const cb = opt.querySelector('input[type="checkbox"]');
            if (cb && cb.checked) cb.click();
        });

        // 精确匹配
        for (const option of options) {
            const optionText = option.textContent.trim().split('\n')[0].trim();
            if (optionText === targetText) {
                const checkbox = option.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.click();
                    console.log(`已选中: ${targetText}`);
                    return true;
                }
            }
        }

        // 大小写模糊匹配
        for (const option of options) {
            const optionText = option.textContent.trim().split('\n')[0].trim();
            if (optionText.toLowerCase() === targetText.toLowerCase()) {
                const checkbox = option.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    checkbox.click();
                    console.log(`模糊匹配已选中: ${optionText}`);
                    return true;
                }
            }
        }

        // 回退到默认值
        if (defaultText) {
            for (const option of options) {
                const optionText = option.textContent.trim().split('\n')[0].trim();
                if (optionText === defaultText) {
                    const checkbox = option.querySelector('input[type="checkbox"]');
                    if (checkbox) {
                        checkbox.click();
                        console.log(`未找到 "${targetText}"，已选中默认值: ${defaultText}`);
                        return true;
                    }
                }
            }
        }

        console.log(`未找到匹配选项: ${targetText}`);
        return false;
    }

    async function callAIForSelection(config, data, availableOptions) {
        const userInputParts = config.inputFields.map(field => {
            const value = data[field.key] || '';
            const processed = field.truncate ? value.substring(0, field.truncate) : value;
            return `${field.label}：${processed}`;
        });

        const optionsList = availableOptions.map((opt, i) => `${i + 1}. ${opt}`).join('\n');

        const messages = [
            {
                role: "system",
                content: config.systemPrompt
            },
            {
                role: "user",
                content: `${config.userPromptPrefix}\n\n${userInputParts.join('\n')}\n\n可选列表（共 ${availableOptions.length} 个选项）：\n${optionsList}\n\n${config.rules}`
            }
        ];

        const response = await fetch(API_CONFIG.baseUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${API_CONFIG.apiKey}`
            },
            body: JSON.stringify({
                model: API_CONFIG.model,
                messages,
                temperature: 0.01,
                max_tokens: 50,
                top_p: 0.1,
                frequency_penalty: 0,
                presence_penalty: 0
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`API 调用失败: ${response.status} - ${errorText}`);
        }

        const result = await response.json();
        return result.choices[0].message.content.trim();
    }

    async function handleAIAttributeSelection(attrName, config, data, container) {
        const hasInput = config.inputFields.some(field => data[field.key]);
        if (!hasInput || !container) {
            console.log(`${attrName} 匹配: 缺少输入数据或容器`);
            return;
        }

        const options = container.querySelectorAll('.choice_btn');
        if (!options || options.length === 0) {
            console.log(`${attrName} 匹配: 没有找到选项按钮`);
            return;
        }

        const availableOptions = extractOptionsFromDOM(container);
        console.log(`${attrName} 可用选项 (${availableOptions.length}):`, availableOptions);

        try {
            const suggested = await callAIForSelection(config, data, availableOptions);
            console.log(`AI 建议的 ${attrName}:`, suggested);
            selectOptionInDOM(container, suggested, config.defaultValue);
        } catch (error) {
            console.error(`${attrName} 匹配失败:`, error);
            selectOptionInDOM(container, config.defaultValue, null);
        }
    }

    // ================= AI 属性配置表 =================

    const AI_ATTRIBUTE_CONFIGS = {
        'Theme': {
            systemPrompt: '你是一个专业的玩具和模型分类专家。根据产品标题和描述，从给定的主题选项中选择最合适的一项。只返回选项列表中存在的完整名称，不要包含任何解释。',
            userPromptPrefix: '请分析以下产品信息并选择最合适的主题：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个名称
2. 优先匹配产品标题中的系列名称
3. 考虑品牌与系列的对应关系（如 Bandai 通常对应 Gundam）
4. 注意第三方品牌的产品归属（如 Cang-Toys 通常属于 Transformers）
5. 如果没有明确对应，返回 "Other Toys"
6. 返回时必须使用与列表中完全相同的名称`,
            inputFields: [
                { key: 'product_title', label: '产品标题' },
                { key: 'description_en', label: '产品描述', truncate: 200 }
            ],
            defaultValue: 'Other Toys'
        },

        'Product Type': {
            systemPrompt: '你是一个专业的玩具和模型分类专家。根据产品标题和搜索关键词，从给定的产品类型选项中选择最合适的一项。只返回选项列表中存在的完整名称，不要包含任何解释。',
            userPromptPrefix: '请分析以下产品信息并选择最合适的产品类型：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个名称
2. 如果是变形金刚相关，注意区分 TF: General / TF: Movie / TF: Beast Wars 等子类型
3. 如果标题包含 Model Kit, MG, RG, HG 等字样，选择 Model Kit
4. 如果是可动人偶且不属于其他特定类别，选择 Action Figure
5. 如果没有明确对应，返回 "Action Figure"
6. 返回时必须使用与列表中完全相同的名称`,
            inputFields: [
                { key: 'product_title', label: '产品标题' },
                { key: 'search_keyword', label: '搜索关键词' }
            ],
            defaultValue: 'Action Figure'
        },

        'Company': {
            systemPrompt: '你是一个玩具和模型品牌专家。根据产品分类，从给定的品牌列表中选择一个最合适的制造商。只返回列表中存在的完整品牌名称，不要添加任何其他内容或解释。',
            userPromptPrefix: '请根据以下产品信息，从品牌列表中选择一个最合适的制造商：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个品牌名称
2. 不要推荐列表之外的品牌
3. 如果没有明确对应的品牌，返回 "Others"
4. 返回时必须使用与列表中完全相同的品牌名称`,
            inputFields: [
                { key: 'category', label: '产品分类' }
            ],
            defaultValue: 'Others'
        },

        'Character': {
            systemPrompt: '你是一个玩具和模型角色专家。根据产品标题，从给定的角色列表中选择最合适的角色。只返回列表中存在的完整角色名称，不要添加任何其他内容或解释。',
            userPromptPrefix: '请根据以下产品信息，从角色列表中选择一个最合适的角色：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个角色名称
2. 不要推荐列表之外的角色
3. 如果没有明确对应的角色，返回 "Others"
4. 返回时必须使用与列表中完全相同的角色名称`,
            inputFields: [
                { key: 'product_title', label: '产品标题' }
            ],
            defaultValue: 'Others'
        },

        'Featured In': {
            systemPrompt: '你是一个玩具和模型系列专家。根据产品标题和搜索关键词，从给定的系列列表中选择最合适的系列。只返回列表中存在的完整系列名称，不要添加任何其他内容或解释。',
            userPromptPrefix: '请根据以下产品信息，从系列列表中选择一个最合适的系列：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个系列名称
2. 不要推荐列表之外的系列
3. 如果没有明确对应的系列，返回 "Others"
4. 返回时必须使用与列表中完全相同的系列名称`,
            inputFields: [
                { key: 'product_title', label: '产品标题' },
                { key: 'search_keyword', label: '搜索关键词' }
            ],
            defaultValue: 'Others'
        },

        'Size': {
            systemPrompt: '你是一个玩具和模型尺寸专家。根据产品描述中提到的高度(Height)或尺寸信息，从给定的尺寸列表中选择最合适的尺寸。只返回列表中存在的完整尺寸名称，不要添加任何其他内容或解释。',
            userPromptPrefix: '请根据以下产品描述，从尺寸列表中选择一个最合适的尺寸：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个尺寸名称
2. 列表中的选项格式为 "Xin / Y.Zcm"（如 "7in / 17.8cm"），返回时必须包含完整的 "Xin / Y.Zcm" 格式
3. 匹配逻辑：从产品描述中提取高度(Height)数值，找到最接近的选项
   - 如果描述中出现英寸数值（如 7"、7 inches、7in），匹配对应的英寸选项
   - 如果描述中只有厘米数值（如 17.8cm），换算为英寸后匹配最接近的选项（1in ≈ 2.54cm）
   - 差异在 1 英寸以内选择最接近的选项
4. 如果描述中同时出现多个尺寸，选择产品整体高度（通常是最大值）
5. 如果没有明确对应，返回列表中的第一个选项
6. 返回时必须使用与列表中完全相同的名称`,
            inputFields: [
                { key: 'description_en', label: '产品描述' }
            ],
            defaultValue: null
        },

        'Scale': {
            systemPrompt: '你是一个玩具和模型比例专家。根据产品描述中提到的比例(Scale)信息，从给定的比例列表中选择最合适的比例。只返回列表中存在的完整比例名称，不要添加任何其他内容或解释。',
            userPromptPrefix: '请根据以下产品描述，从比例列表中选择一个最合适的比例：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个比例名称
2. 优先匹配描述中明确提到的比例信息（如 1/60、1/144、1/100 等）
3. 优先匹配 MP Scale、Leader Class 等特殊系列名称
4. 如果没有明确对应，返回 "Others"
5. 返回时必须使用与列表中完全相同的比例名称`,
            inputFields: [
                { key: 'description_en', label: '产品描述' }
            ],
            defaultValue: 'Others'
        },

        'Hot Categories': {
            systemPrompt: '你是一个专业的玩具和模型分类专家。根据产品标题和描述，从给定的热门分类选项中选择最合适的一项。只返回选项列表中存在的完整名称，不要包含任何解释。',
            userPromptPrefix: '请分析以下产品信息并选择最合适的热门分类：',
            rules: `注意事项：
1. 必须从上述列表中精确选择一个名称
2. 变形金刚、高达、机甲等机器人类产品选择 "Mecha Robot"
3. 动漫周边选择 "Anime/Comics"
4. 美少女手办/机娘选择 "Bishoujo & Mecha Girl"
5. 漫威/DC 等超级英雄选择 "Superheroes"
6. 军事模型选择 "Military"
7. 怪兽/恐怖类选择 "Monsters/Myth & Horror"
8. 游戏周边选择 "Games"
9. 电影/电视剧周边选择 "Movies & TV"
10. 原创设计师玩具选择 "Original/Designer Toys"
11. 如果没有明确对应，返回 "Mecha Robot"
12. 返回时必须使用与列表中完全相同的名称`,
            inputFields: [
                { key: 'product_title', label: '产品标题' },
                { key: 'description_en', label: '产品描述', truncate: 200 }
            ],
            defaultValue: 'Mecha Robot'
        }
    };

    // ================= 标签别名映射（兼容 SZ / GD 不同属性标签） =================

    const LABEL_ALIASES = {
        'Theme':          ['Theme'],
        'Hot Categories': ['Hot Categories'],
        'Product Type':   ['Product Type'],
        'Company':        ['Company', 'Brand'],
        'Character':      ['Character'],
        'Featured In':    ['Featured In'],
        'Size':           ['Size'],
        'Scale':          ['Scale'],
        'Availability':   ['Availability']
    };

    function findAttrContainer(labels, attrName) {
        const aliases = LABEL_ALIASES[attrName] || [attrName];
        for (const alias of aliases) {
            const found = Array.from(labels).find(l => l.textContent.includes(alias));
            if (found) return found.closest('div.rows');
        }
        return null;
    }

    // ================= Availability 处理（纯规则逻辑，不用 AI） =================

    async function handleAvailabilitySelection(data, availabilityContainer) {
        const isComing = data['is_coming'] === '打开';
        const isPresale = data['presale_price'] && parseFloat(data['presale_price']) > 0;
        const stock = parseInt(data['stock'] || '0');

        if (!availabilityContainer) {
            console.log('Availability 匹配: 没有找到容器');
            return;
        }

        const availabilityOptions = availabilityContainer.querySelectorAll('.choice_btn');
        if (!availabilityOptions || availabilityOptions.length === 0) {
            console.log('Availability 匹配: 没有找到选项按钮');
            return;
        }

        const STATUS_MAP = {
            IN_STOCK: 'In Stock',
            SOLD_OUT: 'Sold Out',
            PRE_ORDER: 'Pre-Order',
            COMING_SOON: 'Coming Soon'
        };

        let availabilityStatus = STATUS_MAP.IN_STOCK;

        if (isPresale) {
            availabilityStatus = STATUS_MAP.PRE_ORDER;
        } else if (isComing) {
            availabilityStatus = STATUS_MAP.COMING_SOON;
        } else if (stock <= 0) {
            availabilityStatus = STATUS_MAP.SOLD_OUT;
        }

        console.log('确定的Availability状态:', availabilityStatus, {
            presale_price: data['presale_price'],
            isPresale,
            isComing,
            stock
        });

        for (const option of availabilityOptions) {
            const optionText = option.textContent.trim();
            if (optionText === availabilityStatus) {
                const checkbox = option.querySelector('input[type="checkbox"]');
                if (checkbox) {
                    availabilityOptions.forEach(opt => {
                        const cb = opt.querySelector('input[type="checkbox"]');
                        if (cb && cb.checked) cb.click();
                    });
                    checkbox.click();
                    console.log('已选中Availability:', optionText);
                    return;
                }
            }
        }

        console.log('未找到匹配的Availability，选择默认值');
        const defaultOption = Array.from(availabilityOptions)
            .find(opt => opt.textContent.trim() === STATUS_MAP.IN_STOCK);
        if (defaultOption) {
            const checkbox = defaultOption.querySelector('input[type="checkbox"]');
            if (checkbox) checkbox.click();
        }
    }

    // ================= 表单填充 =================

    async function fillInFields(data, progressBar) {
        const totalFields = 18;
        let filledFields = 0;

        function updateProgress() {
            filledFields++;
            const percent = Math.min(20 + Math.floor((filledFields / totalFields) * 75), 95);
            updateProgressBar(progressBar, percent);
        }

        function fillInput(selectorName, value, clearField = true) {
            return new Promise((resolve, reject) => {
                setTimeout(() => {
                    const inputField = document.getElementsByName(selectorName)[0];
                    if (inputField) {
                        if (clearField) inputField.value = '';
                        inputField.value = value ? String(value) : '';
                        updateProgress();
                        resolve();
                    } else {
                        reject(new Error('未找到输入字段: ' + selectorName));
                    }
                }, 100);
            });
        }

        function toggleCheckbox(selectorName, condition) {
            return new Promise((resolve, reject) => {
                setTimeout(() => {
                    const checkbox = document.getElementsByName(selectorName)[0];
                    if (checkbox) {
                        if (checkbox.checked !== condition) checkbox.click();
                        updateProgress();
                        resolve();
                    } else {
                        reject(new Error('未找到复选框: ' + selectorName));
                    }
                }, 100);
            });
        }

        function selectCategory(categoryName) {
            return new Promise((resolve, reject) => {
                setTimeout(() => {
                    const links = document.querySelectorAll('dd a');
                    let found = false;
                    for (const link of links) {
                        if (link.textContent.includes(categoryName)) {
                            link.click();
                            found = true;
                            updateProgress();
                            resolve();
                            break;
                        }
                    }
                    if (!found) {
                        reject(new Error('未找到对应的分类: ' + categoryName));
                    }
                }, 100);
            });
        }

        try {
            // 分类选择
            if (data['category']) {
                try {
                    await selectCategory(data['category']);
                } catch (error) {
                    console.error('选择分类失败:', error);
                }
            }

            // 基本字段
            await fillInput('Name_en', data['product_title']);
            await fillInput('Number', data['number']);
            await fillInput('SearchKeyword', data['search_keyword']);
            await fillInput('PageUrl', data['page_url']);

            // SEO 标题（分站点后缀）
            let siteSpecificTitle = data['product_title'];
            if (window.location.href.startsWith('https://showzstore.com')) {
                siteSpecificTitle += ' - Show.Z Store';
            } else if (window.location.href.startsWith('https://www.gundamit.com')) {
                siteSpecificTitle += ' - GunDamit Store';
            } else if (window.location.href.startsWith('https://gkloot.com')) {
                siteSpecificTitle += ' | GKLoot.com';
            }
            await fillInput('SeoTitle_en', siteSpecificTitle);

            await fillInput('SeoKeyword_en', data['seo_keyword_en']);
            await fillInput('SeoDescription_en', data['seo_description_en']);

            // 描述内容
            await new Promise((resolve, reject) => {
                setTimeout(() => {
                    const descriptionContent = `<span style="line-height:250%;"><span style="font-size:24px;"><span style="font-family:karla;">${data["description_en"].replace(/\n/g, "<br>")}</span></span></span>`;
                    if (window.CKEDITOR && CKEDITOR.instances['Description_en']) {
                        CKEDITOR.instances['Description_en'].setData(descriptionContent);
                        updateProgress();
                        resolve();
                    } else {
                        reject(new Error('未找到 CKEDITOR 实例: Description_en'));
                    }
                }, 100);
            });

            // 价格和库存
            await fillInput('Price_1', data['price'] ? data['price'] : '0');
            await fillInput('Stock', data['stock'] ? data['stock'] : '20');

            // 复选框
            await toggleCheckbox('IsComing', data['is_coming'] === '打开');
            if (data['presale_price']) {
                await toggleCheckbox('IsPresale', true);
                await fillInput('PresalePrice', data['presale_price']);
            } else {
                await toggleCheckbox('IsPresale', false);
                updateProgress();
            }
            await toggleCheckbox('PreDiscount', data['pre_discount'] === '打开');
            await toggleCheckbox('IsBatteries', data['is_batteries'] === '打开');

            // 尺寸和重量
            await fillInput('Cubage[0]', data['length']);
            await fillInput('Cubage[1]', data['width']);
            await fillInput('Cubage[2]', data['height']);
            await fillInput('Weight', data['weight']);

            // ================= 普通属性（AI 匹配） =================

            const attrLink = document.querySelector('a[data-name="attrbute_info"]');
            if (attrLink) {
                await new Promise(resolve => {
                    attrLink.click();
                    setTimeout(resolve, 1000);
                });

                const labels = document.querySelectorAll('div.rows label');

                // Availability（纯规则逻辑）
                const availabilityContainer = findAttrContainer(labels, 'Availability');
                if (availabilityContainer) {
                    console.log('找到 Availability 容器');
                    await handleAvailabilitySelection(data, availabilityContainer);
                } else {
                    console.log('未找到 Availability 容器');
                }

                // AI 属性统一循环处理（SZ + GD 全集，缺失的自动跳过）
                const AI_ATTRIBUTES = [
                    'Theme', 'Hot Categories', 'Product Type', 'Company',
                    'Character', 'Featured In', 'Size', 'Scale'
                ];
                for (const attrName of AI_ATTRIBUTES) {
                    const attrContainer = findAttrContainer(labels, attrName);
                    if (attrContainer && AI_ATTRIBUTE_CONFIGS[attrName]) {
                        console.log(`找到 ${attrName} 容器`);
                        await handleAIAttributeSelection(attrName, AI_ATTRIBUTE_CONFIGS[attrName], data, attrContainer);
                    } else {
                        console.log(`未找到 ${attrName} 容器（跳过）`);
                    }
                }
            }
        } catch (error) {
            console.error('填写字段时出错:', error);
            throw error;
        }
    }

})();
