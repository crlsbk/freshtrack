plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "mx.freshtrack.mobile"
    compileSdk = 36

    defaultConfig {
        applicationId = "mx.freshtrack.mobile"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // URL del API Gateway (Caddy) desplegado en Google Compute Engine.
        // Se puede cambiar en tiempo de ejecución desde Ajustes → Servidor.
        buildConfigField("String", "DEFAULT_BASE_URL", "\"https://34.51.41.80.nip.io/\"")
    }

    buildTypes {
        debug {
            buildConfigField("boolean", "HTTP_LOGS", "true")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            buildConfigField("boolean", "HTTP_LOGS", "false")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // Firmado con la llave debug para que el APK de release sea instalable en la demo.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    buildFeatures {
        viewBinding = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    implementation(libs.androidx.activity.ktx)
    implementation(libs.androidx.fragment.ktx)
    implementation(libs.androidx.constraintlayout)
    implementation(libs.androidx.lifecycle.viewmodel)
    implementation(libs.androidx.lifecycle.livedata)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.swiperefresh)
    implementation(libs.coroutines.android)

    // Red: Retrofit + OkHttp (JWT, correlation id, manejo de 401)
    implementation(libs.retrofit)
    implementation(libs.retrofit.gson)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)

    // Cámara y escaneo de códigos (QR FT1 firmados, GS1-128, EAN-13)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.view)
    implementation(libs.mlkit.barcode)

    // Alertas en segundo plano
    implementation(libs.work.runtime)
    implementation(libs.androidx.exifinterface)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.coroutines.test)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
