plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    // **The code package.** `--org com.districore.app` appended the pubspec name, giving
    // `com.districore.app.districore`; this is the identifier the ruling approved.
    // `MainActivity.kt` was moved to match — the manifest resolves `.MainActivity` relative
    // to this value, so a namespace without the matching package builds cleanly and dies at
    // launch with ClassNotFoundException.
    namespace = "com.districore.app"
    // Flutter 3.44.7 resolves compileSdk to 36, but the pinned
    // flutter_secure_storage 11.0.0 dependency requires API 37.
    // compileSdk is compile-time only; minSdk and targetSdk remain
    // Flutter's defaults.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // **The install identity, and the intended production identifier.**
        //
        // Chosen, not reserved: nothing in this repository registers it with Google Play or
        // anywhere else, and no such claim should be read into it.
        applicationId = "com.districore.app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        debug {
            // The M8→M9 device gate installs as `com.districore.app.dev`, so a gate build
            // and a production build can coexist on one device and cannot be confused for
            // one another — the gate fills `/data` and kills processes.
            applicationIdSuffix = ".dev"
        }
        release {
            // **No `signingConfig`, deliberately.** The generated line signed release builds
            // with the debug keys so `flutter run --release` would work; that is convenient
            // and wrong. `00` §2.3 / K-1: the release keystore is generated once, stored in
            // the password manager, backed up to two locations that are not this machine,
            // and never committed. It does not exist yet, and nothing here should imply it
            // does. `flutter build apk --release` will refuse until it is supplied — which
            // is the correct failure.
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
