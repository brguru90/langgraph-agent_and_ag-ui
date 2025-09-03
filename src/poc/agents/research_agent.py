import uuid
from typing import Literal,Annotated
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import InjectedState,InjectedStore
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langchain_core import messages
from langchain_core.runnables.config import RunnableConfig
from langgraph.store.base import BaseStore
from .utils import mcp_sampling_handler,get_aws_modal,create_handoff_tool
from fastmcp import Client
from mcp import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
from .state import ChatState,SupervisorNode
from langchain_core.tools import tool
import traceback
import time
from botocore.config import Config


@tool(description="Provide the Guide or steps to run the executable vue3 SFC code as a preview")
def vue3_snippet_preview_guide(
     *,
    config: RunnableConfig,
    state: Annotated[ChatState,InjectedState],
) -> str | list[str | dict]:
    """
    Provide the Guide or steps to run the executable vue3 code as a preview
    """

    brief="""
    # vue3-sfc-loader
    - Vue3/Vue2 Single File Component loader. Load .vue files dynamically at runtime from your html/js. No node.js environment, no (webpack) build step needed.
    - below code provides an example to dynamically run vue3 code in browser, so it can be used to preview code snippet
    - Example1: 
        <html>
        <body>
        <div id="app"></div>
        <script src="https://unpkg.com/vue@latest"></script>
        <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader/dist/vue3-sfc-loader.js"></script>
        <script>

            const options = {
            moduleCache: {
                vue: Vue
            },
            async getFile(url) {
                
                const res = await fetch(url);
                if ( !res.ok )
                throw Object.assign(new Error(res.statusText + ' ' + url), { res });
                return {
                getContentData: asBinary => asBinary ? res.arrayBuffer() : res.text(),
                }
            },
            addStyle(textContent) {

                const style = Object.assign(document.createElement('style'), { textContent });
                const ref = document.head.getElementsByTagName('style')[0] || null;
                document.head.insertBefore(style, ref);
            },
            }

            const { loadModule } = window['vue3-sfc-loader'];

            const app = Vue.createApp({
            components: {
                'my-component': Vue.defineAsyncComponent( () => loadModule('./myComponent.vue', options) )
            },
            template: '<my-component></my-component>'
            });

            app.mount('#app');

        </script>
        </body>
        </html>
    - Example2:
        <!DOCTYPE html>
        <html>
        <body>
        <div id="app"></div>
        <script src="https://unpkg.com/vue@next"></script>
        <script src="https://cdn.jsdelivr.net/gh/FranckFreiburger/vue3-sfc-loader@main/dist/vue3-sfc-loader.js"></script>

        <script>

            // window.localStorage.clear();

            const options = {

            moduleCache: {
                vue: Vue,
            },

            getFile(url) {

                return fetch(url).then(response => response.ok ? response.text() : Promise.reject(response));
            },

            addStyle(styleStr) {

                const style = document.createElement('style');
                style.textContent = styleStr;
                const ref = document.head.getElementsByTagName('style')[0] || null;
                document.head.insertBefore(style, ref);
            },

            log(type, ...args) {

                console.log(type, ...args);
            },

            compiledCache: {
                set(key, str) {

                // naive storage space management
                for (;;) {

                    try {

                    // doc: https://developer.mozilla.org/en-US/docs/Web/API/Storage
                    window.localStorage.setItem(key, str);
                    break;
                    } catch(ex) { // handle: Uncaught DOMException: Failed to execute 'setItem' on 'Storage': Setting the value of 'XXX' exceeded the quota

                    window.localStorage.removeItem(window.localStorage.key(0));
                    }
                }
                },
                get(key) {

                return window.localStorage.getItem(key);
                },
            },

            additionalModuleHandlers: {
                '.json': (source, path, options) => JSON.parse(source),
            }
            }

            // <!--
            const source = `
            <template>
                <div class="example">{{ msg }}</div>
            </template>
            <script>
                export default {
                data () {
                    return {
                    msg: 'Hello world!'
                    }
                }
                }
            </script>

            <style scoped>
                .example {
                color: red;
                }
            </style>
            `;
            // -->


            const { createSFCModule } = window["vue3-sfc-loader"];
            const myComponent = createSFCModule(source, './myComponent.vue', options);

            // ... or by file:
            // const { loadModule } = window["vue3-sfc-loader"];
            // const myComponent = loadModule('./myComponent.vue', options);

            const app = Vue.createApp({
            components: {
                'my-component': Vue.defineAsyncComponent( () => myComponent ),
            },
            template: 'root: <my-component></my-component>'
            });

            app.mount('#app');

        </script>

        </body>
        </html>

        ## key features
        - Supports Vue 3 and Vue 2 (see dist/)
        - Only requires Vue runtime-only build
        - esm and umd bundles available (example)
        - Embedded ES6 modules support ( including import() )
        - TypeScript support, JSX support
        - Custom CSS, HTML and Script language Support, see pug and stylus examples
        - SFC Custom Blocks support
"""

    documentations = """
    

        <!--toc-->
* [Examples](#examples)
  * [Vue2 basic example](#vue2-basic-example)
  * [using esm version](#using-esm-version)
  * [A more complete API usage example](#a-more-complete-api-usage-example)
  * [Load a Vue component from a string](#load-a-vue-component-from-a-string)
  * [Using another template language (pug)](#using-another-template-language-pug)
  * [Using another style language (stylus)](#using-another-style-language-stylus)
  * [SFC style CSS variable injection (new edition)](#sfc-style-css-variable-injection-new-edition)
  * [import style](#import-style)
  * [Minimalist Hello World example](#minimalist-hello-world-example)
  * [Use `options.loadModule` hook](#use-optionsloadmodule-hook)
  * [Dynamic component (using `:is` Special Attribute)](#dynamic-component-using-is-special-attribute)
  * [Nested components](#nested-components)
  * [Use SFC Custom Blocks for i18n](#use-sfc-custom-blocks-for-i18n)
  * [Use Options.getResource() and process the files (nearly) like webpack does](#use-optionsgetresource-and-process-the-files-nearly-like-webpack-does)
  * [Load SVG dynamically (using `watch()`)](#load-svg-dynamically-using-watch)
  * [Load SVG dynamically (using `async setup()` and `<Suspense>`)](#load-svg-dynamically-using-async-setup-and-suspense)
  * [Use remote components](#use-remote-components)
  * [image loading](#image-loading)
  * [IE11 example](#ie11-example)
<!--/toc-->

find [more examples here](https://github.com/FranckFreiburger/vue3-sfc-loader/discussions/categories/examples)

# Examples

:warning: **beware**, the following examples are sticky to version *<!--version-->0.9.5<!--/version-->*. For your use, you would prefer the [latest version](../README.md#dist)

**Try the examples locally**  
Since most browsers do not allow you to access local filesystem, you can start a small [express](https://expressjs.com/) server to run these examples.  
Run the following commands to start a basic web server on port `8181`:
```sh
npm install express  # or yarn add express
node -e "require('express')().use(require('express').static(__dirname, {index:'index.html'})).listen(8181)"
```

**note:**  
In the following examples, for convenience, we just returns static content as file. In real world, you would probably use something like this :
```javascript
  ...
  async getFile(url) {

    const res = await fetch(url);

    if ( !res.ok ) {

      throw Object.assign(new Error(res.statusText + ' ' + url), { res });
    }

    return {
      getContentData: (asBinary) => asBinary ? res.arrayBuffer() : res.text(),
    }

  },
  ...
```


## Vue2 basic example

**note:** Vue2 do not have the `Vue.defineAsyncComponent()` function. Here we mount the app when the main component is ready.

<!--example:source:vue2_basic_example-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <script src="https://unpkg.com/vue@2/dist/vue.runtime.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue2-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const mainComponent = `
      <template>
        <span>Hello from Vue {{ require('myData').vueVersion }} !</span>
      </template>
    `;
    /* --> */

    const { loadModule, vueVersion } = window['vue2-sfc-loader'];

    const options = {
      moduleCache: {
        vue: Vue,
        myData: {
          vueVersion,
        }
      },
      getFile(url) {

        if ( url === '/main.vue' )
          return Promise.resolve(mainComponent);
      },
      addStyle() { /* unused here */ },
    }

    loadModule('/main.vue', options)
    .then(component => new Vue(component).$mount('#app'));
  </script>
</body>
</html>
```

[:top:](#readme)


## using esm version

<!--example:source:esm_version_example-->
```html
<!DOCTYPE html>
<html>
<body>
  <script type="module">

    import * as Vue from 'https://unpkg.com/vue@3/dist/vue.runtime.esm-browser.prod.js'
    import { loadModule } from 'https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.esm.js'

    const options = {
      moduleCache: { vue: Vue },
      getFile: () => `<template>vue3-sfc-loader esm version</template>`,
      addStyle: () => {},
    }
    Vue.createApp(Vue.defineAsyncComponent(() => loadModule('file.vue', options))).mount(document.body);

  </script>
</body>
</html>
```

[:top:](#readme)


## A more complete API usage example

<!--example:source:complete_api-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <!-- here we need to load Vue3 full version because we use template:'...' -->
  <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    const componentSource = /* <!-- */`
      <template>
        <span class="example">{{ msg }}</span>
      </template>
      <script>
        export default {
          data () {
            return {
              msg: 'world!'
            }
          }
        }
      </script>

      <style scoped>
        .example {
          color: red;
        }
      </style>
    `/* --> */;

    const options = {

      moduleCache: {
        vue: Vue,
      },

      async getFile(url) {

        if ( url === '/myComponent.vue' )
          return Promise.resolve(componentSource);

        const res = await fetch(url);
        if ( !res.ok )
          throw Object.assign(new Error(url+' '+res.statusText), { res });
        return await res.text();
      },

      addStyle(textContent) {

        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
      },

      log(type, ...args) {

        console[type](...args);
      },

      compiledCache: {
        set(key, str) {

          // naive storage space management
          for (;;) {

            try {

              // doc: https://developer.mozilla.org/en-US/docs/Web/API/Storage
              window.localStorage.setItem(key, str);
              break;
            } catch(ex) {

              // handle: Uncaught DOMException: Failed to execute 'setItem' on 'Storage': Setting the value of 'XXX' exceeded the quota

              window.localStorage.removeItem(window.localStorage.key(0));
            }
          }
        },
        get(key) {

          return window.localStorage.getItem(key) ?? undefined;
        },
      },

      handleModule(type, source, path, options) {
        
        if ( type === '.json' )
          return JSON.parse(source);
      }
    }

    const { loadModule } = window['vue3-sfc-loader'];
    const myComponent = loadModule('/myComponent.vue', options);

    const app = Vue.createApp({
      components: {
        'my-component': Vue.defineAsyncComponent( () => myComponent ),
      },
      template: 'Hello <my-component></my-component>'
    });

    app.mount('#app');

  </script>

</body>
</html>
```

[:top:](#readme)


## Load a Vue component from a string

<!--example:source:cpn_string-->
```html
<!DOCTYPE html>
<html>
<body>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const sfcContent = `
      <template>
        Hello World !
      </template>
    `;
    /* --> */

    const options = {
      moduleCache: {
        vue: Vue,
      },
      getFile(url) {

        if ( url === '/myComponent.vue' )
          return Promise.resolve(sfcContent);
      },
      addStyle() { /* unused here */ },
    }

    const { loadModule } = window['vue3-sfc-loader'];
    Vue.createApp(Vue.defineAsyncComponent(() => loadModule('/myComponent.vue', options))).mount(document.body);

  </script>
</body>
</html>
```

[:top:](#readme)


## Using another template language (pug)

<!--example:source:tpl_pug-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://pugjs.org/js/pug.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const sfcContent = `
<template lang="pug">
ul
  each val in ['p', 'u', 'g']
    li= val
</template>
`;
    /* --> */

    const options = {

      moduleCache: {
        vue: Vue,
        pug: require('pug'),
      },

      getFile(url) {

        if ( url === '/myPugComponent.vue' )
          return Promise.resolve(sfcContent);
      },

      addStyle: () => {},
    }

    const { loadModule } = window["vue3-sfc-loader"];
    Vue.createApp(Vue.defineAsyncComponent(() => loadModule('/myPugComponent.vue', options))).mount('#app');

  </script>
</body>
</html>

```

[:top:](#readme)


## Using another style language (stylus)

<!--example:source:style_stylus-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script src="//stylus-lang.com/try/stylus.min.js"></script>
  <script>

    /* <!-- */
    const vueContent = `
      <template>
        Hello <b>World</b> !
      </template>
      <style lang="stylus">
 b
  color red
      </style>
    `;
    /* --> */

    const options = {
      moduleCache: {
        vue: Vue,
        // note: deps() does not work in this bundle of stylus (see https://stylus-lang.com/docs/js.html#deps)
        stylus: source => Object.assign(stylus(source), { deps: () => [] }),
      },
      getFile: () => vueContent,
      addStyle(styleStr) {
        const style = document.createElement('style');
        style.textContent = styleStr;
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
      },
    }

    Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('file.vue', options))).mount(document.body);

  </script>
</body>
</html>

```

[:top:](#readme)


## SFC style CSS variable injection (new edition)

_see at [vuejs/rfcs](https://github.com/vuejs/rfcs/pull/231)_

<!--example:source:rfc_231-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>
    /* <!-- */
    const sfcContent = `
      <template>
        Hello <span class="example">{{ msg }}</span>
      </template>
      <script>
        export default {
          data () {
            return {
              msg: 'world!',
              color: 'blue',
            }
          }
        }
      </script>
      <style scoped>
        .example {
          color: v-bind('color')
        }
      </style>
    `;
    /* --> */

    const options = {
      moduleCache: {
        vue: Vue,
      },
      getFile(url) {

        if ( url === '/myComponent.vue' )
          return Promise.resolve(sfcContent);
      },
      addStyle(textContent) {

        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
      },
    }

    const { loadModule } = window["vue3-sfc-loader"];
    Vue.createApp(Vue.defineAsyncComponent(() => loadModule('/myComponent.vue', options))).mount('#app');
  </script>
</body>
</html>
```

[:top:](#readme)


## import style

<!--example:source:import_style-->
```html
<!DOCTYPE html>
<html>
<body>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const config = {
      
      // note: Here, for convenience, we simply retrieve content from a string.
      
      files: {

        '/style.css': `
          .styled { color: red }
        `,

        '/main.vue': `
          <template>
            <span class="styled">hello</span> world
          </template>
          <script>
            import './style.css'
            export default {
            }
          </script>
        `,
      }
    };
    /* --> */

    const options = {
      moduleCache: { vue: Vue },
      getFile: url => config.files[url],
      addStyle(textContent) {

        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
      },
      handleModule: async function (type, getContentData, path, options) { 
        switch (type) { 
          case '.css':
            options.addStyle(await getContentData(false));
            return null;
        } 
      },
    }

    Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('/main.vue', options))).mount(document.body);

  </script>
</body>
</html>
```


[:top:](#readme)


## Minimalist Hello World example

<!--example:source:minimalist_example-->
```html
<!DOCTYPE html>
<html>
<body>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    const options = {
      moduleCache: { vue: Vue },
      getFile: () => `<template>Hello World !</template>`,
      addStyle: () => {},
    }
    Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('file.vue', options))).mount(document.body);

  </script>
</body>
</html>
```

[:top:](#readme)



## Use `options.loadModule` hook

<!--example:source:options_loadModule-->
```html
<!DOCTYPE html>
<html>
<body>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const sfcContent = `
      <template>
        Hello World !
      </template>
    `;
    /* --> */

    const options = {
      moduleCache: { vue: Vue },
      async loadModule(path) {

        // (TBD)

      },
      getFile(url) {

        if ( url === '/myComponent.vue' )
          return Promise.resolve(sfcContent);
      },
      addStyle() { /* unused here */ },
    }

    const { loadModule } = window['vue3-sfc-loader'];
    Vue.createApp(Vue.defineAsyncComponent(() => loadModule('/myComponent.vue', options))).mount(document.body);

  </script>
</body>
</html>
```

[:top:](#readme)



## Dynamic component (using `:is` Special Attribute)

In the following example we use a trick to preserve reactivity through the `Vue.defineAsyncComponent()` call (see the following [discussion](https://github.com/FranckFreiburger/vue3-sfc-loader/discussions/6))

<!--example:source:dynamic_component-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <!-- here we need to load Vue3 full version because we use template:'...' -->
  <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    const options = {

      moduleCache: {
        vue: Vue,
      },

      getFile(url) {
        
        // note: Here, for convenience, we simply retrieve content from a string.
        
        return ({
          '/a.vue': `
            <template>
              <i> a </i>
            </template>
          `,
          '/b.vue': `
            <template>
              <b> b </b>
            </template>
          `,
        })[url] || Promise.reject( new Error(res.statusText) );
      },

      addStyle() { /* unused here */ },
    }

    const { loadModule } = window["vue3-sfc-loader"];

    const app = Vue.createApp({
      template: `
        <button
          @click="currentComponent = currentComponent === 'a' ? 'b' : 'a'"
        >toggle</button>
        dynamic component: <component :is="comp"></component>
      `,
      computed: {
        comp() {

          const currentComponent = this.currentComponent; // the trick is here
          return Vue.defineAsyncComponent( () => loadModule(`/${ currentComponent }.vue`, options) );

          // or, equivalently, use Function.prototype.bind function like this:
          // return Vue.defineAsyncComponent( (url => loadModule(url, options)).bind(null, `/${ this.currentComponent }.vue`) );
        }
      },
      data() {
        return {
          currentComponent: 'a',
        }
      }
    });

    app.mount('#app');

  </script>
</body>
</html>
```

[:top:](#readme)




## Nested components

<!--example:source:nested_components-->
```html
<!DOCTYPE html>
<html>
<body>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const config = {
      
      // note: Here, for convenience, we simply retrieve content from a string.
      
      files: {
        '/main.vue': `
            <template>
                <foo/>
            </template>
            <script>
                import foo from './foo.vue'

                export default {
                    components: {
                        foo,
                    },
                    created() {
                        console.log('main created')
                    },
                    mounted() {
                        console.log('main mounted')
                    }
                }
            </script>
        `,

        '/foo.vue': `
            <template>
                <bar/>
            </template>
            <script>
                import bar from './bar.vue'

                export default {
                    components: {
                        bar,
                    },
                    created() {
                        console.log('foo created')
                    },
                    mounted() {
                        console.log('foo mounted')
                    }
                }
            </script>
        `,

        '/bar.vue': `
            <template>
                end
            </template>
            <script>

                export default {
                    components: {
                    },
                    created() {
                        console.log('bar created')
                    },
                    mounted() {
                        console.log('bar mounted')
                    }
                }
            </script>
        `
      }
    };
    /* --> */


    const options = {
      moduleCache: { vue: Vue },
      getFile: url => config.files[url],
      addStyle: () => {},
    }

    Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('/main.vue', options))).mount(document.body);

  </script>
</body>
</html>
```

[:top:](#readme)




## Use SFC Custom Blocks for i18n

<!--example:source:custom_block_i18n-->
```html
<!DOCTYPE html>
<html>
<body>
  <script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
  <script src="https://unpkg.com/vue-i18n@latest"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
  <script>

    /* <!-- */
    const config = {
      
      // note: Here, for convenience, we simply retrieve content from a string.
      
      files: {
        '/component.vue': `
          <template>
            {{ $t('hello') }}
          </template>
          <i18n>
          {
            "en": {
              "hello": "hello world!"
            },
            "ja": {
              "hello": "こんにちは、世界！"
            }
          }
          </i18n>
       `
      }
    };
    /* --> */

    const i18n = VueI18n.createI18n();

    const options = {
      moduleCache: { vue: Vue },
      getFile: url => config.files[url],
      addStyle: () => {},
      customBlockHandler(block, filename, options) {

        if ( block.type !== 'i18n' )
          return

        const messages = JSON.parse(block.content);
        for ( let locale in messages )
          i18n.global.mergeLocaleMessage(locale, messages[locale]);
      }
    }

    const app = Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('/component.vue', options)));

    app.use(i18n);

    app.mount(document.body);

  </script>
</body>
</html>
```


[:top:](#readme)


## Use Options.getResource() and process the files (nearly) like webpack does

<!--example:source:getResource_loaders-->
```html
<!DOCTYPE html>
<html>
<body>
<script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
<script>

  const config = {
    files: {
      
      // note: Here, for convenience, we simply retrieve content from a string.

      '/main.vue': {
        getContentData: () => /* <!-- */`
          <template>
            <pre><b>'url!./circle.svg' -> </b>{{ require('url!./circle.svg') }}</pre>
            <img width="50" height="50" src="~url!./circle.svg" />
            <pre><b>'file!./circle.svg' -> </b>{{ require('file!./circle.svg') }}</pre>
            <img width="50" height="50" src="~file!./circle.svg" /> <br><i>(image failed to load, this is expected since there is nothing behind this url)</i>
          </template>
        `/* --> */,
        type: '.vue',
      },
      '/circle.svg': {
        getContentData: () => /* <!-- */`
          <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
            <circle cx="50" cy="50" r="50" />
          </svg>
        `/* --> */,
        type: '.svg',
      }
    }
  };
  
  const options = {
    moduleCache: {
      'vue': Vue,
      'file!'(content, path, type, options) {

        return String(new URL(path, window.location));
      },
      'url!'(content, path, type, options) {

        if ( type === '.svg' )
          return `data:image/svg+xml;base64,${ btoa(content) }`;

        throw new Error(`${ type } not handled by url!`);
      },
    },
    handleModule(type, getContentData, path, options) {

      switch (type) {
        case '.svg': return getContentData(false);
        default: return undefined; // let vue3-sfc-loader handle this
      }
    },
    getFile(url, options) {

      return config.files[url] || (() => { throw new Error('404 ' + url) })();
    },
    getResource({ refPath, relPath }, options) {

      const { moduleCache, pathResolve, getFile } = options;

      // split relPath into loaders[] and file path (eg. 'foo!bar!file.ext' => ['file.ext', 'bar!', 'foo!'])
      const [ resourceRelPath, ...loaders ] = relPath.match(/([^!]+!)|[^!]+$/g).reverse();

      // helper function: process a content through the loaders
      const processContentThroughLoaders = (content, path, type, options) => {
        
        return loaders.reduce((content, loader) => {

          return moduleCache[loader](content, path, type, options);
        }, content);
      }

      // get the actual path of the file
      const path = pathResolve({ refPath, relPath: resourceRelPath }, options);

      // the resource id must be unique in its path context
      const id = loaders.join('') + path;

      return {
        id,
        path,
        async getContent() {

          const { getContentData, type } = await getFile(path);
          return {
            getContentData: async (asBinary) => processContentThroughLoaders(await getContentData(asBinary), path, type, options),
            type,
          };
        }
      };
    },
    addStyle() { /* unused here */ },
  }

  const { loadModule } = window['vue3-sfc-loader'];
  Vue.createApp(Vue.defineAsyncComponent(() => loadModule('/main.vue', options))).mount(document.body);

</script>
</body>
</html>
```


[:top:](#readme)


## Load SVG dynamically (using `watch()`)

<!--example:source:load_svg_watch-->
```html
<!DOCTYPE html>
<html>
<body>
<script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
<script>

  /* <!-- */
  const config = {
    
    // note: Here, for convenience, we simply retrieve content from a string.

    files: {
      '/circle0.svg': `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="50" /></svg>`,
      '/circle1.svg': `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="40" /></svg>`,
      '/main.vue': `
        <template>
          <mycomponent
            :name="'circle' + index % 2"
          />
        </template>
        <script>
          import mycomponent from './myComponent.vue'
          import { ref } from 'vue'

          export default {
            components: {
              mycomponent
            },
            setup() {
              
              const index = ref(0);
              setInterval(() => index.value++, 1000);
              return {
                index,
              }
            },
          }
        </script>
      `,
      '/myComponent.vue': `
        <template>
          <span v-html="svg" />
        </template>
        <script>

          import { ref, watch } from 'vue'

          function asyncToRef(callback) {

            const val = ref();
            watch(() => callback(), promise => promise.then(value => val.value = value), { immediate: true });  // TBD handle catch()...
            return val;
          }

          export default {
            props: {
              name: String
            },
            setup(props) {
              return {
                svg: asyncToRef(() => import('./' + props.name + '.svg')),
              }
            }
          }

        </script>
      `
    }
  };
  /* --> */

  const options = {
    moduleCache: { vue: Vue },
    getFile: url => config.files[url],
    addStyle(textContent) {

      const style = Object.assign(document.createElement('style'), { textContent });
      const ref = document.head.getElementsByTagName('style')[0] || null;
      document.head.insertBefore(style, ref);
    },
    handleModule: async function (type, getContentData, path, options) { 
      switch (type) { 
        case '.svg':
          return getContentData(false);
      } 
    },
  }

  Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('/main.vue', options))).mount(document.body);

</script>

</body>
</html>
```


[:top:](#readme)



## Load SVG dynamically (using `async setup()` and `<Suspense>`)

<!--example:source:load_svg_async_setup-->
```html
<!DOCTYPE html>
<html>
<body>
<script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
<script>

  /* <!-- */
  const config = {

    // note: Here, for convenience, we simply retrieve content from a string.

    files: {
      '/circle.svg': `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="50" /></svg>`,
      '/main.vue': `
        <template>
          <Suspense>
            <mycomponent
              :name="'circle'"
            />
          </Suspense>
        </template>
        <script>
          import mycomponent from './myComponent.vue'
          export default {
            components: {
              mycomponent
            },
          }
        </script>
      `,
      '/myComponent.vue': `
        <template>
          <span v-html="svg"/>
        </template>
        <script>
          export default {
            props: {
              name: String
            },
            async setup(props) {
              return {
                svg: await import('./' + props.name + '.svg'),
              }
            }
          }
        </script>        
      `
    }
  };
  /* --> */

  const options = {
    moduleCache: { vue: Vue },
    getFile: url => config.files[url],
    addStyle(textContent) {

      const style = Object.assign(document.createElement('style'), { textContent });
      const ref = document.head.getElementsByTagName('style')[0] || null;
      document.head.insertBefore(style, ref);
    },
    handleModule: async function (type, getContentData, path, options) { 
      switch (type) { 
        case '.svg':
          return getContentData(false);
      } 
    },
  }

  Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('/main.vue', options))).mount(document.body);

</script>

</body>
</html>
```


[:top:](#readme)




## Use remote components

Here we import [vue-calendar-picker](https://github.com/FranckFreiburger/vue-calendar-picker) and also manage the **date-fns** dependent module.  
This example use Vue2 because **vue-calendar-picker** is written for Vue2.

<!--example:source:remote_vue_components-->
```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <script src="https://unpkg.com/vue@2/dist/vue.runtime.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue2-sfc-loader.js"></script>
  <script>
    
    const options = {
      moduleCache: {
        vue: Vue,
        'date-fns/locale/en/index.js': {}, // handle require('date-fns/locale/' + this.locale.toLowerCase() + '/index.js');
      },
      pathResolve({ refPath, relPath }, options) {

        if ( relPath === 'date-fns' )
          return 'https://cdnjs.cloudflare.com/ajax/libs/date-fns/1.30.1/date_fns.min.js';

        if ( relPath === '.' ) // self
          return refPath;
        
        // relPath is a module name ?
        if ( relPath[0] !== '.' && relPath[0] !== '/' )
          return relPath;

        return String(new URL(relPath, refPath === undefined ? window.location : refPath));
      },
      getFile: async (url) => {

        // note: here, for convinience, we just returns a content from a string

        if ( new URL(url).pathname === '/main.vue' ) {

          return {
            getContentData: () => /*<!--*/`
              <template>
                <div>
                  <calendar-range locale="EN" :selection="selection" :events="calendarEvents"/>
                  <button @click="add">add</button>
                </div>
              </template>
              <script>
                import calendarRange from 'https://raw.githubusercontent.com/FranckFreiburger/vue-calendar-picker/v1.2.1/src/calendarRange.vue'

                export default {
                  components: {
                    calendarRange,
                  },
                  data: {
                    selection: { start: Date.now(), end: Date.now() },
                    calendarEvents: []
                  },
                  methods: {
                    add: function() {
                      this.calendarEvents.push({
                        color: '#'+Math.floor(Math.random()*16777215).toString(16),
                        start: this.selection.start,
                        end: this.selection.end
                      });
                    }
                  }
                }
              </script>
            `/* --> */,
            type: '.vue',
          }
        }

        return fetch(url).then(res => res.text());
      },
      addStyle(textContent) {

        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
      },
    }

    const { loadModule } = window['vue2-sfc-loader'];

    loadModule('/main.vue', options)
    .then(component => new Vue(component).$mount('#app'))

  </script>

</body>
</html>
```


[:top:](#readme)


## image loading

<!--example:source:image_loading-->
```html
<!DOCTYPE html>
<html>
<body>
<script src="https://unpkg.com/vue@3/dist/vue.runtime.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue3-sfc-loader.js"></script>
<script>

  /* <!-- */
  const config = {
    files: {
      
      // note: Here, for convenience, we simply retrieve content from a string.

      '/theComponent.vue': `
        <script setup>

          const pngData = await import('https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png')
          
          // crate an ObjectURL of our image
          const pngBlobUrl = URL.createObjectURL(new Blob([pngData]));

          // cleanup the ObjectURL, see https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL_static#memory_management
          const onImageLoaded = (ev) => URL.revokeObjectURL(ev.target.src);

        </script>

        <template>
          image loaded by the browser, the usual way:
          <img src="https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png"/>
          <hr/>
          image loaded by vue3-sfc-loader through <pre>fetch()</pre>:
          <img @load="onImageLoaded" :src="pngBlobUrl" />
        </template>

        <style>
          img { width: 128px; vertical-align: middle; }
          pre { display: inline; }
        </style>
      `,
      
      '/main.vue': `
        <script setup>
          import theComponent from '/theComponent.vue'
        </script>
        <template>
          <Suspense>
            <theComponent/>
          </Suspense>
        </template>
      `,
    }
  };
  /* --> */

  const options = {
    devMode: true,
    moduleCache: {
      vue: Vue,
    },
    async getFile(url) {
      
      if ( config.files[url] )
        return config.files[url];
      
      const res = await fetch(url);
      if ( !res.ok )
        throw Object.assign(new Error(res.statusText + ' ' + url), { res });
      return {
        getContentData: asBinary => asBinary ? res.arrayBuffer() : res.text(),
      }
    },

    addStyle(textContent) {

      const style = Object.assign(document.createElement('style'), { textContent });
      const ref = document.head.getElementsByTagName('style')[0] || null;
      document.head.insertBefore(style, ref);
    },

    handleModule: async function (type, getContentData, path, options) {

      switch (type) { 
        case '.png':
          return getContentData(true); // load as binary
      } 
    },

    log(type, ...args) {

      console[type](...args);
    }
  }

  const app = Vue.createApp(Vue.defineAsyncComponent(() => window['vue3-sfc-loader'].loadModule('/main.vue', options)))
  app.mount(document.body);

</script>

</body>
</html>
```


[:top:](#readme)


## IE11 example

```html
<!DOCTYPE html>
<html>
<body>
  <div id="app"></div>
  <script src="https://unpkg.com/vue@2/dist/vue.runtime.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vue3-sfc-loader@0.9.5/dist/vue2-sfc-loader.js"></script>
  <script>

    const config = {
      
      // note: Here, for convenience, we simply retrieve content from a string.

      files: {
        /* <!-- */
        '/app.vue': ''
        + '  <template>                                                           ' 
        + '    <div>{{ index }}</div>                                             '
        + '  </template>                                                          '
        + '  <script>                                                             '
        + '                                                                       '
        + '    export default {                                                   '
        + '      data() {                                                         '
        + '        return {                                                       '
        + '          index: 0,                                                    '
        + '        }                                                              '
        + '      },                                                               '
        + '      async mounted() {                                                '
        + '                                                                       '
        + '        for ( ; this.index < 100; ++this.index )                       '
        + '          await new Promise(resolve => setTimeout(resolve, 1000));     '
        + '      }                                                                '
        + '    }                                                                  '
        + '  </script>                                                            '
        /* --> */
      }
    };
    
    const options = {
      moduleCache: { vue: Vue },
      getFile: function(url) { return config.files[url] },
      addStyle: function () {},
    }

    window['vue2-sfc-loader'].loadModule('/app.vue', options)
    .then(function(app) {
      new Vue(app).$mount('#app')
    });
    
  </script>
</body>
</html>
```

[:top:](#readme)

    """

    msg= messages.HumanMessage(
        content=f"Here is the documentations only extract the required information based on the user query:\n {brief+documentations}",
        id=str(uuid.uuid4())
    )
    try:
        return get_aws_modal().invoke(state["messages"]+[msg]).content
    except Exception as e:
        print(f"Error invoking AWS modal: {e}")
        return brief

class ResearchAgent:

    def __init__(self, return_to_supervisor=False):
        print("__ResearchAgent__")
        self.return_to_supervisor = return_to_supervisor
        self.base_llm = None
        self.llm = None
        self.tools = None
        self.tool_node = None
        self.graph = None
        self.client:Client = None
        self.client_session:ClientSession = None
        self.name:str=SupervisorNode.RESEARCH_AGENT_VAL
        self.descriptions="provide the generic documentations related to software coding, Note: the tools in this agent returns huge information so decide tool call based on token limits."

    def get_steering_tool(self):
        return create_handoff_tool(agent_name=self.name, description=f"Assign task to a researcher agent ({self.descriptions}).")

    async def llm_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """LLM node - only responsible for calling llm.invoke"""
        
        chat_messages = state["messages"]
        for msg in chat_messages:
            if not hasattr(msg, 'id') or msg.id is None:
                msg.id = str(uuid.uuid4())
        try:
            response = await self.llm.ainvoke(chat_messages)
        except Exception as e:
            print(f"Error invoking LLM: {e}\n", chat_messages, traceback.print_exc())
            response = messages.AIMessage(content=f"An error occurred while processing your request. Please try again later. {e}", id=str(uuid.uuid4()))
        
        updated_messages = chat_messages + [response]

        return Command(
            update={
                'messages': updated_messages,
            },
            goto="route"
        )

    async def tools_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["route"]]:
        """Tools node - only responsible for calling tool_node.ainvoke"""    
        ai_msg: messages.AIMessage = state["messages"][-1]
        result = await self.tool_node.ainvoke(state)

        # Combine all messages for the updated state
        all_updated_messages = state['messages'] + result['messages']
        
        return Command(
            update={
                'messages': all_updated_messages,
                'tool_call_count': state['tool_call_count'] + 1
            },
            goto="route"
        )

    def route_node(self, state: ChatState, config: RunnableConfig, *, store: BaseStore) -> Command[Literal["tools", "llm"]]:
        """Route node - handles all routing logic using Command pattern"""
        
        last_message = state['messages'][-1]

        print(f"--route_node research_agent: message_type={type(last_message).__name__}, tool_count={state['tool_call_count']}, has_tool_calls={hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}, message_type_attr={getattr(last_message, 'type', 'no_type')}, len={len(state['messages'])}", last_message)
        
        # Normal flow routing logic:
        # 1. If last message is AIMessage with tool_calls → go to tools
        # 2. If last message is ToolMessage → go to LLM (to process tool results)
        # 3. If last message is AIMessage without tool_calls → end (LLM finished)
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            # LLM wants to use tools
            return Command(
                update={},
                goto="tools"
            )
        elif last_message.type == 'tool':
            # Tool message completed, let LLM process the results
            return Command(
                update={},
                goto="llm"
            )
        else:
            # LLM finished without tool calls - end execution
            return Command(
                update={},
                goto=END
            )

    async def init(self):
        """Initialize the agent with MCP tools and LLM"""
        
        # Initialize LLMs
        botocore_cfg = Config(connect_timeout=30, read_timeout=60, retries={'max_attempts': 0})

        self.base_llm = get_aws_modal(config=botocore_cfg)

        mcp_config={
                "context7": {
                    "url": "https://mcp.context7.com/mcp",
                    "transport": "http",
                }
        }
        # self.client=Client(mcp_config,sampling_handler=mcp_sampling_handler)   
        # max_conn_retry=20
        # while max_conn_retry>=0 and not self.client_session :
        #   try:
        #       print("max_conn_retry",max_conn_retry)
        #       self.client_session = (await self.client.__aenter__()).session
        #       break
        #   except Exception as e:
        #       time.sleep(0.2)
        #       max_conn_retry-=1
        self.tools=[]
        # self.tools.extend(await load_mcp_tools(self.client_session))   
        # if self.tools:
        #     print(f"Successfully loaded {len(self.tools)} MCP tools")
        # else:
        #     raise ValueError("No tools loaded, returning...")
        
        self.tools.append(vue3_snippet_preview_guide)

        for tool in self.tools:
            tool.name=self.name+"_"+tool.name
        # Bind tools to LLM and create tool node
        self.llm = self.base_llm.bind_tools(self.tools)
        self.tool_node = ToolNode(self.tools)

        # Build the graph using StateGraph
        builder = StateGraph(ChatState)
        builder.add_node('llm', self.llm_node)
        builder.add_node('tools', self.tools_node)
        builder.add_node('route', self.route_node)        

        builder.add_edge(START, 'llm')
        builder.add_edge("route", END)

        self.graph = builder.compile(name=self.name)
        self.graph.get_graph().print_ascii()

    async def close(self):
        """Clean up resources and close connections"""
        print("Closing agent resources...")
        await self.__aexit__(None, None, None)

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources and close connections"""
        import asyncio
        import warnings
        
        # Suppress warnings during cleanup
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # Close client session first
            if self.client_session:
                try:
                    print("Closing client session...")
                    await asyncio.wait_for(
                        self.client_session.__aexit__(exc_type, exc_val, exc_tb),
                        timeout=2.0  # Give it 2 seconds to close gracefully
                    )
                    print("Client session closed successfully")
                except asyncio.TimeoutError:
                    print("Client session close timed out, forcing cleanup")
                except Exception as e:
                    print(f"Error closing client session: {e}")
                finally:
                    self.client_session = None
            
            # Clean up the main client (no __aexit__ method available)
            if self.client:
                self.client.close()
                self.client = None
        
        print("Agent cleanup completed")