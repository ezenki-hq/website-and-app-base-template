FROM nginx:1.30-alpine

COPY . /context

RUN test ! -e /context/.dart_tool/context-sentinel \
    && test ! -e /context/build/context-sentinel \
    && test ! -e /context/.pub-cache/context-sentinel \
    && test ! -e /context/.env.context-sentinel \
    && test ! -e /context/.idea/context-sentinel \
    && test ! -e /context/.vscode/context-sentinel \
    && test ! -e /context/android/.gradle/context-sentinel \
    && test ! -e /context/android/app/build/context-sentinel \
    && test ! -e /context/ios/Pods/context-sentinel \
    && test ! -e /context/ios/.symlinks/context-sentinel \
    && test ! -e /context/ios/Flutter/ephemeral/context-sentinel
